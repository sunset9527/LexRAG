import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { clearRuntimeCredentials, setRuntimeApiKey } from '@/security/runtimeCredentials'

export interface LLMProvider {
  key: string
  label: string
  baseUrl: string
  models: string[]
}

export const LLM_PROVIDERS: LLMProvider[] = [
  { key: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com', models: ['deepseek-v4-pro', 'deepseek-v4-flash'] },
  { key: 'qwen', label: '通义千问', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-turbo', 'qwen-plus', 'qwen-max'] },
  { key: 'glm', label: '智谱 GLM', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', models: ['glm-4', 'glm-4-flash'] },
  { key: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', models: ['gpt-4o', 'gpt-4o-mini'] },
  { key: 'claude', label: 'Claude', baseUrl: 'https://api.anthropic.com', models: ['claude-sonnet-5-20251001', 'claude-haiku-4-5-20251001'] },
  { key: 'custom', label: '自定义', baseUrl: '', models: [] },
]

export const useSettingsStore = defineStore('settings', () => {
  // 非敏感偏好可从 localStorage 恢复；API Key 始终从空的会话内存开始。
  const provider = ref(localStorage.getItem('lexrag_provider') || 'deepseek')
  const model = ref(localStorage.getItem('lexrag_model') || 'deepseek-v4-pro')
  const apiKey = ref('')
  const baseUrl = ref(localStorage.getItem('lexrag_base_url') || 'https://api.deepseek.com')

  // 只持久化非敏感偏好。
  watch(provider, (v) => localStorage.setItem('lexrag_provider', v))
  watch(model, (v) => localStorage.setItem('lexrag_model', v))
  watch(apiKey, (v) => setRuntimeApiKey(v), { immediate: true })
  watch(baseUrl, (v) => localStorage.setItem('lexrag_base_url', v))

  const currentProvider = () => LLM_PROVIDERS.find((p) => p.key === provider.value)

  function switchProvider(key: string) {
    const p = LLM_PROVIDERS.find((x) => x.key === key)
    if (p) {
      provider.value = key
      baseUrl.value = p.baseUrl
      if (p.models.length > 0) {
        model.value = p.models[0]
      }
    }
  }

  function clearApiKey() {
    apiKey.value = ''
    clearRuntimeCredentials()
  }

  return {
    provider,
    model,
    apiKey,
    baseUrl,
    currentProvider,
    switchProvider,
    clearApiKey,
  }
})
