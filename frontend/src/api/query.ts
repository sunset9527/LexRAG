/**
 * 法律问答 API
 */
import client from './client'

export interface QueryRequest {
  query: string
  session_id?: string
  config?: Record<string, any>
}

export interface Citation {
  article_id: string
  citation_text: string
  original_text: string
  is_verified: boolean
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
  metadata: Record<string, any>
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

  getGraph(): Promise<GraphData> {
    return client.get('/graph').then((r) => r.data)
  },

  queryGraph(params: { article_id?: string; source?: string; target?: string }): Promise<any> {
    return client.post('/graph/query', params).then((r) => r.data)
  },

  getHealth(): Promise<any> {
    return client.get('/health').then((r) => r.data)
  },
}
