/**
 * 法律问答 API
 */
import client from './client'
import { buildQueryRunEventsUrl, parseEventPayload } from './sseProtocol'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

export interface QueryRequest {
  query: string
  session_id?: string
  config?: Record<string, any>
  knowledge_base_ids?: string[]
  case_date?: string
}

export interface Citation {
  article_id: string
  citation_text: string
  original_text: string
  is_verified: boolean
  version_id?: string
  effective_from?: string
  effective_to?: string
  source_url?: string
  content_hash?: string
  knowledge_base_slug?: string
  source_type?: string
  retrieval_paths?: string[]
}

export interface WorkflowTraceEvent {
  node: string
  status: 'completed' | 'degraded' | 'failed' | 'skipped'
  duration_ms: number
  input_count: number
  output_count: number
  reason?: string
}

export interface WorkflowMetadata {
  workflow_version?: string
  workflow_status?: 'completed' | 'degraded'
  verification_attempts?: number
  evidence_count?: number
  verification_summary?: string
  workflow_trace?: WorkflowTraceEvent[]
  cache_hit?: 'exact' | 'semantic'
  cache_original_query?: string
  cache_similarity?: number
  version_selection?: VersionSelection
  version_selections?: Record<string, VersionSelection>
  knowledge_base_routing?: {
    mode: 'automatic' | 'explicit' | 'clarification'
    selected_slugs: string[]
    candidates: Array<{ slug: string; confidence: number; reason_code: string }>
  }
  [key: string]: unknown
}

export interface VersionTimelineItem {
  target_version_id: string
  effective_from: string
  effective_to: string | null
}

export interface VersionSelection {
  version_id: string
  effective_from: string
  effective_to: string
  source_url: string
  content_hash: string
  as_of: string
  assumption: string | null
  timeline: VersionTimelineItem[]
}

export interface QueryResponse {
  query_id: string
  query: string
  answer: string
  intent: string
  citations: Citation[]
  verification_status: string
  verification_issues: string[]
  sub_questions: Array<{ question: string; answer: string }>
  metadata: WorkflowMetadata
}

export interface QueryRunAccepted {
  query_id: string
}

export interface QueryRunStageEvent {
  stage: string
  status: 'completed' | 'degraded' | 'failed' | 'skipped'
  duration_ms?: number
  input_count?: number
  output_count?: number
  reason?: string
}

export interface QueryRunCompletedEvent {
  response: Omit<QueryResponse, 'query'>
}

export interface QueryRunSubscriptionHandlers {
  onStage?: (event: QueryRunStageEvent) => void
  onCompleted?: (event: QueryRunCompletedEvent) => void
  onCancelled?: () => void
  onFailed?: (code: string) => void
  onConnectionError?: () => void
}

export interface LawDocument {
  content: string
  law_name: string
  version?: string
}

export interface GraphData {
  statistics: Record<string, any>
  most_cited: Array<{ article: string; count: number }>
  visualization_data: any
}

export const queryApi = {
  ask(data: QueryRequest): Promise<QueryResponse> {
    return client.post('/query', data).then((r) => r.data)
  },

  createRun(data: QueryRequest): Promise<QueryRunAccepted> {
    return client.post('/query-runs', data).then((r) => r.data)
  },

  subscribeToRun(queryId: string, handlers: QueryRunSubscriptionHandlers): () => void {
    const source = new EventSource(buildQueryRunEventsUrl(API_BASE_URL, queryId), {
      withCredentials: true,
    })
    const listen = <T>(eventName: string, handler?: (payload: T) => void) => {
      source.addEventListener(eventName, (event) => {
        const payload = parseEventPayload((event as MessageEvent<string>).data) as T | null
        if (payload) handler?.(payload)
      })
    }
    listen<QueryRunStageEvent>('stage_completed', handlers.onStage)
    listen<QueryRunCompletedEvent>('completed', handlers.onCompleted)
    source.addEventListener('cancelled', () => handlers.onCancelled?.())
    listen<{ code?: string }>('failed', (event) => handlers.onFailed?.(event.code || 'QUERY_FAILED'))
    source.onerror = () => handlers.onConnectionError?.()
    return () => source.close()
  },

  cancelRun(queryId: string): Promise<{ query_id: string; cancelled: boolean }> {
    return client.post(`/query-runs/${encodeURIComponent(queryId)}/cancel`).then((r) => r.data)
  },

  uploadLaw(data: LawDocument): Promise<any> {
    return client.post('/upload', data).then((r) => r.data)
  },

  getGraph(lawName?: string): Promise<GraphData & { available_laws?: string[] }> {
    return client.get('/graph', { params: lawName ? { law_name: lawName } : undefined }).then((r) => r.data)
  },

  queryGraph(params: { article_id?: string; source?: string; target?: string }): Promise<any> {
    return client.post('/graph/query', params).then((r) => r.data)
  },

  getHealth(): Promise<any> {
    return client.get('/health').then((r) => r.data)
  },
}
