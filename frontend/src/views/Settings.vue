<template>
  <div class="settings-page">
    <h2>⚙️ 设置</h2>

    <!-- LLM 提供商 -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <span style="font-weight:600;">🤖 LLM 提供商</span>
          <el-button type="primary" size="small" @click="saveLLMSettings" :loading="savingLLM">
            💾 保存设置
          </el-button>
          <el-button size="small" @click="clearApiKey">清除本次 API Key</el-button>
        </div>
      </template>

      <ProviderSelector
        :model-value="draftProvider"
        :providers="LLM_PROVIDERS"
        @update:model-value="selectProvider"
      />

      <el-form label-width="100px" style="margin-top: 20px;">
        <el-form-item label="Base URL">
          <el-input v-model="draftBaseUrl" placeholder="https://api.deepseek.com" />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="draftModel" placeholder="deepseek-v4-pro" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="draftApiKey"
            type="password"
            placeholder="sk-xxx 填入你自己的 DeepSeek API Key"
            show-password
          />
          <div class="form-hint">
            ⚠️ API Key 仅保存在你的浏览器中，通过请求 header 传到后端，不会存储在服务器上
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Prompt 管理 -->
    <el-card shadow="never" class="settings-card" style="margin-top: 20px;">
      <template #header>
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <span style="font-weight:600;">📝 Prompt 管理</span>
          <el-button size="small" type="primary" @click="showCreatePrompt = true">
            新建 Prompt
          </el-button>
        </div>
      </template>

      <el-table :data="prompts" stripe style="width:100%" v-loading="promptsLoading">
        <el-table-column prop="name" label="名称" width="180" />
        <el-table-column prop="description" label="描述" min-width="200" />
        <el-table-column prop="category" label="分类" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.category || '未分类' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="80" align="center">
          <template #default="{ row }">
            v{{ row.version }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }">
            <el-button size="small" @click="editPrompt(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑 Prompt 对话框 -->
    <el-dialog
      v-model="showCreatePrompt"
      :title="editingPrompt ? '编辑 Prompt' : '新建 Prompt'"
      width="700px"
    >
      <el-form :model="promptForm" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="promptForm.name" :disabled="!!editingPrompt" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="promptForm.category" placeholder="选择分类">
            <el-option label="agent" value="agent" />
            <el-option label="generation" value="generation" />
            <el-option label="retrieval" value="retrieval" />
            <el-option label="verification" value="verification" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="promptForm.description" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input
            v-model="promptForm.content"
            type="textarea"
            :rows="14"
            placeholder="Prompt 模板内容…"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreatePrompt = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="savePrompt">
          {{ editingPrompt ? '更新（版本+1）' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useSettingsStore, LLM_PROVIDERS } from '@/stores/settings'
import { promptsApi, type PromptData } from '@/api/prompts'
import ProviderSelector from '@/components/settings/ProviderSelector.vue'

const settingsStore = useSettingsStore()

// ========== LLM 设置草稿（点保存才生效） ==========
const draftProvider = ref(settingsStore.provider)
const draftModel = ref(settingsStore.model)
const draftApiKey = ref(settingsStore.apiKey)
const draftBaseUrl = ref(settingsStore.baseUrl)
const savingLLM = ref(false)

function selectProvider(key: string) {
  draftProvider.value = key
  const p = LLM_PROVIDERS.find((x) => x.key === key)
  if (p) {
    draftBaseUrl.value = p.baseUrl
    if (p.models.length > 0) draftModel.value = p.models[0]
  }
}

function saveLLMSettings() {
  settingsStore.provider = draftProvider.value
  settingsStore.model = draftModel.value
  settingsStore.apiKey = draftApiKey.value
  settingsStore.baseUrl = draftBaseUrl.value
  // 手动触发 localStorage 持久化（store 的 watch 会自动执行）
  savingLLM.value = true
  setTimeout(() => {
    savingLLM.value = false
    ElMessage.success('LLM 设置已保存，下次请求生效')
  }, 300)
}

function clearApiKey() {
  settingsStore.clearApiKey()
  draftApiKey.value = ''
  ElMessage.success('本次会话的 API Key 已清除')
}

// ========== Prompt 管理 ==========
const prompts = ref<PromptData[]>([])
const promptsLoading = ref(false)
const showCreatePrompt = ref(false)
const editingPrompt = ref<PromptData | null>(null)
const saving = ref(false)

const promptForm = reactive({
  name: '',
  category: '',
  description: '',
  content: '',
})

async function loadPrompts() {
  promptsLoading.value = true
  try {
    const res = await promptsApi.list()
    prompts.value = res.prompts
  } catch {
    // 静默
  } finally {
    promptsLoading.value = false
  }
}

function editPrompt(row: PromptData) {
  editingPrompt.value = row
  promptForm.name = row.name
  promptForm.category = row.category || ''
  promptForm.description = row.description || ''
  promptForm.content = row.content
  showCreatePrompt.value = true
}

async function savePrompt() {
  saving.value = true
  try {
    if (editingPrompt.value) {
      await promptsApi.update(editingPrompt.value.name, {
        content: promptForm.content,
        description: promptForm.description,
      })
      ElMessage.success(`Prompt 已更新（v${editingPrompt.value.version + 1}）`)
    } else {
      await promptsApi.create({
        name: promptForm.name,
        content: promptForm.content,
        description: promptForm.description,
        category: promptForm.category,
      })
      ElMessage.success('Prompt 已创建')
    }
    showCreatePrompt.value = false
    editingPrompt.value = null
    await loadPrompts()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadPrompts)
</script>

<style scoped>
.settings-page { max-width: 960px; margin: 0 auto; }
.settings-page h2 { font-size: 20px; color: #0f1f3d; margin: 0 0 20px; }

.settings-card { border-radius: 12px; }

.form-hint { font-size: 12px; color: #c0c4cc; margin-top: 4px; }
</style>
