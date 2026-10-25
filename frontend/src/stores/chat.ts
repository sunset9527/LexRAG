import { defineStore } from 'pinia'
import { ref } from 'vue'
import { queryApi, type QueryResponse, type Citation, type VersionSelection, type WorkflowTraceEvent, type QueryRunStageEvent } from '@/api/query'
import { sessionsApi, type Recommendation, type SessionSummary } from '@/api/sessions'

export interface KnowledgeBaseRouteCandidate {
  slug: string
  confidence: number
  reason_code: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  intent?: string
  verificationStatus?: string
  workflowTrace?: WorkflowTraceEvent[]
  workflowStatus?: 'completed' | 'degraded'
  evidenceCount?: number
  verificationAttempts?: number
  knowledgeBaseSlug?: string
  cacheHit?: 'exact' | 'semantic'
  cacheOriginalQuery?: string
  cacheSimilarity?: number
  versionSelection?: VersionSelection
  knowledgeBaseRouting?: QueryResponse['metadata']['knowledge_base_routing']
  routingCandidates?: KnowledgeBaseRouteCandidate[]
  timestamp: number
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)
  const currentSessionId = ref<string | null>(null)
  const sessions = ref<SessionSummary[]>([])
  const recommendations = ref<Recommendation[]>([])
  const activeQueryId = ref<string | null>(null)
  const activeStages = ref<QueryRunStageEvent[]>([])
  const activeRunStartedAt = ref<number | null>(null)
  const streamStatus = ref<'idle' | 'running' | 'reconnecting' | 'cancelled'>('idle')

  function generateId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
  }

  async function sendMessage(question: string, knowledgeBaseIds?: string[], caseDate?: string): Promise<void> {
    // 添加用户消息
    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: question,
      timestamp: Date.now(),
    }
    messages.value.push(userMsg)

    isLoading.value = true
    activeRunStartedAt.value = Date.now()

    try {
      const accepted = await queryApi.createRun({
        query: question,
        session_id: currentSessionId.value || undefined,
        knowledge_base_ids: knowledgeBaseIds?.length ? knowledgeBaseIds : undefined,
        case_date: caseDate || undefined,
      })
      activeQueryId.value = accepted.query_id
      activeStages.value = []
      streamStatus.value = 'running'

      const res = await new Promise<Omit<QueryResponse, 'query'>>((resolve, reject) => {
        const unsubscribe = queryApi.subscribeToRun(accepted.query_id, {
          onStage: (event) => activeStages.value.push(event),
          onCompleted: (event) => {
            unsubscribe()
            resolve(event.response)
          },
          onCancelled: () => {
            unsubscribe()
            streamStatus.value = 'cancelled'
            reject(new Error('QUERY_CANCELLED'))
          },
          onFailed: (code) => {
            unsubscribe()
            reject(new Error(code))
          },
          onConnectionError: () => {
            streamStatus.value = 'reconnecting'
          },
        })
      })

      // 保存 sessionId
      if (res.query_id && !currentSessionId.value) {
        currentSessionId.value = res.query_id
      }

      // 添加助手消息
      const assistantMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: res.answer,
        citations: res.citations,
        intent: res.intent,
        verificationStatus: res.verification_status,
        workflowTrace: res.metadata?.workflow_trace || [],
        workflowStatus: res.metadata?.workflow_status,
        evidenceCount: res.metadata?.evidence_count,
        verificationAttempts: res.metadata?.verification_attempts,
        knowledgeBaseSlug: knowledgeBaseIds?.join('|'),
        cacheHit: res.metadata?.cache_hit,
        cacheOriginalQuery: res.metadata?.cache_original_query,
        cacheSimilarity: res.metadata?.cache_similarity,
        versionSelection: res.metadata?.version_selection,
        knowledgeBaseRouting: res.metadata?.knowledge_base_routing,
        timestamp: Date.now(),
      }
      messages.value.push(assistantMsg)
      await loadSessions()
    } catch (error) {
      if (error instanceof Error && error.message === 'QUERY_CANCELLED') {
        messages.value.push({
          id: generateId(),
          role: 'assistant',
          content: '已取消本次查询；系统未保存未完成回答。',
          timestamp: Date.now(),
        })
        return
      }
      const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      const clarification = detail && typeof detail === 'object'
        ? detail as { code?: string; message?: string; candidates?: unknown }
        : undefined
      const routingCandidates = clarification?.code === 'KNOWLEDGE_BASE_CLARIFICATION_REQUIRED'
        && Array.isArray(clarification.candidates)
        ? clarification.candidates.filter((item): item is KnowledgeBaseRouteCandidate => {
            return Boolean(item)
              && typeof item === 'object'
              && typeof (item as KnowledgeBaseRouteCandidate).slug === 'string'
          })
        : undefined
      const errorMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: clarification?.message || '抱歉，处理请求时出现了错误。请稍后重试。',
        routingCandidates,
        timestamp: Date.now(),
      }
      messages.value.push(errorMsg)
    } finally {
      isLoading.value = false
      activeQueryId.value = null
      activeRunStartedAt.value = null
      if (streamStatus.value !== 'cancelled') streamStatus.value = 'idle'
    }
  }

  async function cancelActiveQuery(): Promise<void> {
    if (!activeQueryId.value) return
    await queryApi.cancelRun(activeQueryId.value)
  }

  function clearMessages() {
    messages.value = []
    currentSessionId.value = null
  }

  async function loadSessions(query?: string) {
    sessions.value = await sessionsApi.list(query)
  }

  async function loadSession(sessionId: string) {
    const detail = await sessionsApi.get(sessionId)
    currentSessionId.value = detail.id
    messages.value = detail.messages.flatMap((item) => {
      const timestamp = item.created_at ? Date.parse(item.created_at) : Date.now()
      return [
        { id: `user_${item.id}`, role: 'user' as const, content: item.question, timestamp },
        {
          id: `assistant_${item.id}`,
          role: 'assistant' as const,
          content: item.answer,
          citations: item.citations,
          intent: item.intent || undefined,
          verificationStatus: item.verification_status || undefined,
          workflowTrace: item.metadata?.workflow_trace || [],
          workflowStatus: item.metadata?.workflow_status,
          evidenceCount: item.metadata?.evidence_count,
          verificationAttempts: item.metadata?.verification_attempts,
          versionSelection: item.metadata?.version_selection,
          knowledgeBaseRouting: item.metadata?.knowledge_base_routing,
          timestamp,
        },
      ]
    })
  }

  async function createSession() {
    const session = await sessionsApi.create()
    currentSessionId.value = session.id
    messages.value = []
    await loadSessions()
    return session
  }

  async function archiveSession(sessionId: string) {
    await sessionsApi.archive(sessionId)
    if (currentSessionId.value === sessionId) clearMessages()
    await loadSessions()
  }

  async function renameSession(sessionId: string, title: string) {
    await sessionsApi.rename(sessionId, title)
    await loadSessions()
  }

  async function loadRecommendations() {
    recommendations.value = (await sessionsApi.recommendations()).items
  }

  return {
    messages,
    isLoading,
    currentSessionId,
    sessions,
    recommendations,
    activeQueryId,
    activeStages,
    activeRunStartedAt,
    streamStatus,
    sendMessage,
    cancelActiveQuery,
    clearMessages,
    loadSessions,
    loadSession,
    createSession,
    archiveSession,
    renameSession,
    loadRecommendations,
  }
})
