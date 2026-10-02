import client from './client'
import type { Citation, WorkflowMetadata } from './query'

export interface SessionSummary {
  id: string
  title: string
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export interface SessionMessage {
  id: number
  question: string
  answer: string
  intent: string | null
  citations: Citation[]
  verification_status: string | null
  metadata: WorkflowMetadata
  created_at: string | null
}

export interface SessionDetail extends SessionSummary {
  messages: SessionMessage[]
}

export interface Recommendation {
  type: string
  label: string
  path?: string
  questions?: string[]
}

export const sessionsApi = {
  create(initial_question?: string): Promise<SessionSummary> {
    return client.post('/sessions', { initial_question }).then((r) => r.data)
  },
  list(query?: string): Promise<SessionSummary[]> {
    return client.get('/sessions', { params: query ? { q: query } : undefined }).then((r) => r.data.items)
  },
  get(sessionId: string): Promise<SessionDetail> {
    return client.get(`/sessions/${sessionId}`).then((r) => r.data)
  },
  rename(sessionId: string, title: string): Promise<SessionSummary> {
    return client.patch(`/sessions/${sessionId}`, { title }).then((r) => r.data)
  },
  archive(sessionId: string): Promise<void> {
    return client.delete(`/sessions/${sessionId}`)
  },
  recommendations(): Promise<{ based_on_law_area: string; items: Recommendation[] }> {
    return client.get('/recommendations').then((r) => r.data)
  },
}
