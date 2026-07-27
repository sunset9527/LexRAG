/**
 * Prompt 管理 API
 */
import client from './client'

export interface PromptData {
  id: number
  name: string
  content: string
  version: number
  description: string | null
  category: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface PromptListResponse {
  total: number
  prompts: PromptData[]
}

export const promptsApi = {
  list(): Promise<PromptListResponse> {
    return client.get('/prompts').then((r) => r.data)
  },

  get(name: string): Promise<PromptData> {
    return client.get(`/prompts/${name}`).then((r) => r.data)
  },

  create(data: { name: string; content: string; description?: string; category?: string }): Promise<PromptData> {
    return client.post('/prompts', data).then((r) => r.data)
  },

  update(name: string, data: { content: string; description?: string }): Promise<PromptData> {
    return client.put(`/prompts/${name}`, data).then((r) => r.data)
  },

  delete(name: string): Promise<{ message: string }> {
    return client.delete(`/prompts/${name}`).then((r) => r.data)
  },

  history(name: string): Promise<{ name: string; total_versions: number; versions: PromptData[] }> {
    return client.get(`/prompts/${name}/history`).then((r) => r.data)
  },
}
