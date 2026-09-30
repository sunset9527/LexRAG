import { defineStore } from 'pinia'
import { ref } from 'vue'
import { queryApi, type QueryResponse, type Citation } from '@/api/query'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  intent?: string
  verificationStatus?: string
  trace?: Array<{
    step_type: string
    description: string
    confidence: number
  }>
  knowledgeBaseSlug?: string
  cacheHit?: 'exact' | 'semantic'
  cacheOriginalQuery?: string
  cacheSimilarity?: number
  timestamp: number
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)
  const currentSessionId = ref<string | null>(null)
  const sessions = ref<Array<{ id: string; title: string; updatedAt: number }>>([])

  function generateId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
  }

  async function sendMessage(question: string, knowledgeBaseId?: string): Promise<void> {
    // 添加用户消息
    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: question,
      timestamp: Date.now(),
    }
    messages.value.push(userMsg)

    isLoading.value = true

    try {
      const res: QueryResponse = await queryApi.ask({
        query: question,
        session_id: currentSessionId.value || undefined,
        knowledge_base_ids: knowledgeBaseId ? [knowledgeBaseId] : undefined,
      })

      // 保存 sessionId
      if (res.query_id && !currentSessionId.value) {
        currentSessionId.value = res.query_id
        sessions.value.unshift({
          id: res.query_id,
          title: question.slice(0, 30) + (question.length > 30 ? '…' : ''),
          updatedAt: Date.now(),
        })
      }

      // 添加助手消息
      const assistantMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: res.answer,
        citations: res.citations,
        intent: res.intent,
        verificationStatus: res.verification_status,
        trace: res.metadata?.reasoning_trace || [],
        knowledgeBaseSlug: knowledgeBaseId,
        cacheHit: res.metadata?.cache_hit,
        cacheOriginalQuery: res.metadata?.cache_original_query,
        cacheSimilarity: res.metadata?.cache_similarity,
        timestamp: Date.now(),
      }
      messages.value.push(assistantMsg)
    } catch (error) {
      const errorMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: '抱歉，处理请求时出现了错误。请稍后重试。',
        timestamp: Date.now(),
      }
      messages.value.push(errorMsg)
    } finally {
      isLoading.value = false
    }
  }

  function clearMessages() {
    messages.value = []
    currentSessionId.value = null
  }

  function loadSession(sessionId: string) {
    currentSessionId.value = sessionId
    // 实际会话加载需要后端 /history API（v2.4 实现）
  }

  return {
    messages,
    isLoading,
    currentSessionId,
    sessions,
    sendMessage,
    clearMessages,
    loadSession,
  }
})
