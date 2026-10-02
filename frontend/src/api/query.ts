/**
 * 法律问答 API
 */
import client from './client'

export interface QueryRequest {
  query: string
  session_id?: string
  config?: Record<string, any>
  knowledge_base_ids?: string[]
}

export interface Citation {
  article_id: string
  citation_text: string
  original_text: string
  is_verified: boolean
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
  [key: string]: unknown
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
