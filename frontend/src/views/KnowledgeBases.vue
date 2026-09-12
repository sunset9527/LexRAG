<template>
  <section class="page">
    <header><h1>知识库管理</h1><p>管理法规库的索引状态与数据规模。</p><el-button type="primary" @click="dialogVisible = true">创建法规库</el-button></header>
    <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" />
    <el-table :data="items" v-loading="loading" empty-text="暂无知识库，请先创建并索引法规文本。">
      <el-table-column prop="name" label="知识库" min-width="210" />
      <el-table-column prop="law_area" label="领域" width="110" />
      <el-table-column label="状态" width="130">
        <template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="document_count" label="法条数" width="100" />
      <el-table-column prop="chunk_count" label="Chunk 数" width="110" />
      <el-table-column label="最近索引" min-width="180">
        <template #default="{ row }">{{ row.last_indexed_at || '尚未索引' }}</template>
      </el-table-column>
      <el-table-column label="失败原因" min-width="180">
        <template #default="{ row }">{{ row.error_message || '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="210" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" :disabled="row.status === 'INDEXING'" @click="pickFile(row.slug)">重建</el-button>
          <el-button text type="danger" :disabled="row.status === 'INDEXING'" @click="remove(row.slug, row.name)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <input ref="fileInput" type="file" accept=".txt,text/plain" hidden @change="rebuildFromFile" />
    <el-dialog v-model="dialogVisible" title="创建法规知识库" width="440px">
      <el-form label-position="top"><el-form-item label="名称"><el-input v-model="form.name" /></el-form-item><el-form-item label="唯一标识（小写英文，用连字符分隔）"><el-input v-model="form.slug" /></el-form-item><el-form-item label="法律领域"><el-input v-model="form.law_area" /></el-form-item></el-form>
      <template #footer><el-button @click="dialogVisible=false">取消</el-button><el-button type="primary" :loading="saving" @click="create">创建</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { knowledgeBaseApi, type KnowledgeBase } from '@/api/knowledgeBases'

const items = ref<KnowledgeBase[]>([])
const loading = ref(false)
const error = ref('')
const dialogVisible = ref(false)
const saving = ref(false)
const fileInput = ref<HTMLInputElement>()
const rebuildingSlug = ref('')
const form = ref({ name: '', slug: '', law_area: '' })
const statusText = (status: KnowledgeBase['status']) => ({ EMPTY: '待索引', INDEXING: '索引中', READY: '可用', FAILED: '失败' })[status]
const statusType = (status: KnowledgeBase['status']) => ({ EMPTY: 'info', INDEXING: 'warning', READY: 'success', FAILED: 'danger' }[status])

async function load() {
  loading.value = true
  try { items.value = await knowledgeBaseApi.list() }
  catch { error.value = '知识库列表加载失败，请确认后端服务与数据库已启动。' }
  finally { loading.value = false }
}
async function create() { saving.value = true; try { await knowledgeBaseApi.create(form.value); dialogVisible.value = false; await load(); ElMessage.success('法规库已创建，请上传 .txt 原文后重建索引。') } finally { saving.value = false } }
function pickFile(slug: string) { rebuildingSlug.value = slug; fileInput.value?.click() }
async function rebuildFromFile(event: Event) { const file = (event.target as HTMLInputElement).files?.[0]; if (!file) return; const content = await file.text(); await knowledgeBaseApi.rebuild(rebuildingSlug.value, content); await load(); ElMessage.success('索引重建完成'); (event.target as HTMLInputElement).value = '' }
async function remove(slug: string, name: string) { await ElMessageBox.confirm(`删除“${name}”会同时删除其向量索引，且不可恢复。`, '确认删除', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }); await knowledgeBaseApi.remove(slug); await load(); ElMessage.success('知识库已删除') }
onMounted(load)
</script>

<style scoped>
.page { max-width: 1240px; margin: 0 auto; }
h1 { margin: 0; color: #0f1f3d; font-family: 'Noto Serif SC', STSong, serif; }
header { margin-bottom: 24px; } header p { color: #606266; }
</style>
