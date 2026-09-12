<template>
  <section class="page">
    <header><div><h1>文档解析中心</h1><p>将 PDF/Word 异步解析、分块并入库。任务状态由 Redis + Celery Worker 驱动。</p></div><el-button type="primary" @click="createVisible = true">创建文档库</el-button></header>
    <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" />
    <el-empty v-if="!loading && libraries.length === 0" description="暂无自定义文档库，请先创建一个知识库。" />
    <template v-else>
      <el-select v-model="selectedSlug" placeholder="选择文档库" class="library-select" @change="loadJobs"><el-option v-for="item in libraries" :key="item.slug" :label="item.name" :value="item.slug" /></el-select>
      <el-card v-if="selectedSlug" class="upload-card" shadow="never"><el-form inline><el-form-item label="分块大小"><el-input-number v-model="chunkSize" :min="200" :max="2000" /></el-form-item><el-form-item label="重叠字符"><el-input-number v-model="chunkOverlap" :min="0" :max="chunkSize - 1" /></el-form-item><el-form-item><input ref="fileInput" type="file" accept=".pdf,.docx" hidden @change="upload" /><el-button type="primary" :loading="uploading" @click="fileInput?.click()">上传 PDF / Word</el-button></el-form-item></el-form></el-card>
      <el-table :data="jobs" v-loading="loading" empty-text="该知识库还没有上传文件。"><el-table-column prop="original_filename" label="源文件" min-width="230" /><el-table-column prop="file_type" label="格式" width="80" /><el-table-column label="状态" width="150"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusText(row.status) }} {{ row.progress }}%</el-tag></template></el-table-column><el-table-column label="解析统计" min-width="170"><template #default="{ row }">{{ stats(row) }}</template></el-table-column><el-table-column prop="error_message" label="失败原因" min-width="180" /><el-table-column label="操作" width="100" fixed="right"><template #default="{ row }"><el-button v-if="row.status === 'FAILED'" text type="warning" @click="retry(row.id)">重试</el-button></template></el-table-column></el-table>
    </template>
    <el-dialog v-model="createVisible" title="创建自定义文档库" width="440px"><el-form label-position="top"><el-form-item label="名称"><el-input v-model="form.name" /></el-form-item><el-form-item label="唯一标识"><el-input v-model="form.slug" /></el-form-item><el-form-item label="法律领域"><el-input v-model="form.law_area" /></el-form-item></el-form><template #footer><el-button @click="createVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="createLibrary">创建</el-button></template></el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { documentApi, type DocumentJob } from '@/api/documents'
import { knowledgeBaseApi, type KnowledgeBase } from '@/api/knowledgeBases'

const libraries = ref<KnowledgeBase[]>([]); const jobs = ref<DocumentJob[]>([]); const selectedSlug = ref(''); const loading = ref(false); const uploading = ref(false); const saving = ref(false); const error = ref(''); const createVisible = ref(false); const fileInput = ref<HTMLInputElement>(); const chunkSize = ref(800); const chunkOverlap = ref(120); const form = ref({ name: '', slug: '', law_area: '' }); let timer: number | undefined
const hasActiveJob = computed(() => jobs.value.some(job => ['UPLOADED', 'PARSING', 'CHUNKING', 'INDEXING'].includes(job.status)))
const statusText = (status: DocumentJob['status']) => ({ UPLOADED: '已接收', PARSING: '解析中', CHUNKING: '分块中', INDEXING: '入库中', READY: '已完成', FAILED: '失败' })[status]
const statusType = (status: DocumentJob['status']) => ({ UPLOADED: 'info', PARSING: 'warning', CHUNKING: 'warning', INDEXING: 'warning', READY: 'success', FAILED: 'danger' }[status])
const stats = (job: DocumentJob) => `${job.page_count ?? '—'} 页 · ${job.character_count ?? '—'} 字 · ${job.chunk_count ?? '—'} chunks`
async function loadLibraries() { loading.value = true; try { libraries.value = (await knowledgeBaseApi.list()).filter(item => item.type === 'document'); if (!selectedSlug.value && libraries.value[0]) selectedSlug.value = libraries.value[0].slug; if (selectedSlug.value) await loadJobs() } catch { error.value = '文档库列表加载失败，请确认后端服务已启动。' } finally { loading.value = false } }
async function loadJobs() { if (!selectedSlug.value) return; jobs.value = await documentApi.list(selectedSlug.value); if (hasActiveJob.value && timer === undefined) timer = window.setInterval(loadJobs, 2000); if (!hasActiveJob.value && timer !== undefined) { window.clearInterval(timer); timer = undefined } }
async function createLibrary() { saving.value = true; try { const library = await documentApi.createLibrary(form.value); createVisible.value = false; selectedSlug.value = library.slug; form.value = { name: '', slug: '', law_area: '' }; await loadLibraries(); ElMessage.success('文档库已创建') } finally { saving.value = false } }
async function upload(event: Event) { const file = (event.target as HTMLInputElement).files?.[0]; if (!file || !selectedSlug.value) return; uploading.value = true; try { await documentApi.upload(selectedSlug.value, file, chunkSize.value, chunkOverlap.value); await loadJobs(); ElMessage.success('文件已进入异步解析队列') } finally { uploading.value = false; (event.target as HTMLInputElement).value = '' } }
async function retry(id: string) { await documentApi.retry(id); await loadJobs(); ElMessage.success('已重新投递任务') }
onMounted(loadLibraries); onBeforeUnmount(() => { if (timer !== undefined) window.clearInterval(timer) })
</script>

<style scoped>.page { max-width: 1240px; margin: 0 auto; } header { margin-bottom: 24px; display: flex; justify-content: space-between; align-items: flex-start; } h1 { margin: 0; color: #0f1f3d; font-family: 'Noto Serif SC', STSong, serif; } p { color: #606266; }.library-select { width: 320px; margin-bottom: 16px; }.upload-card { margin-bottom: 16px; }</style>
