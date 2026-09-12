import client from './client'

export interface KnowledgeBase {
  id: string
  name: string
  slug: string
  type: string
  law_area: string
  collection_name: string
  status: 'EMPTY' | 'INDEXING' | 'READY' | 'FAILED'
  document_count: number
  chunk_count: number
  last_indexed_at: string | null
  error_message: string | null
}

export interface LawArticle { id: string; article_number?: number | string; content: string }

export const knowledgeBaseApi = {
  list: () => client.get<{ items: KnowledgeBase[] }>('/knowledge-bases').then(r => r.data.items),
  laws: (slug: string, range?: { startArticle: number; endArticle: number }) => client.get<{ items: LawArticle[] }>(`/knowledge-bases/${slug}/laws`, {
    params: range ? { start_article: range.startArticle, end_article: range.endArticle } : undefined,
  }).then(r => r.data.items),
  create: (data: { name: string; slug: string; law_area: string }) => client.post<KnowledgeBase>('/knowledge-bases', data).then(r => r.data),
  rebuild: (slug: string, content: string) => client.post<KnowledgeBase>(`/knowledge-bases/${slug}/rebuild`, { content }).then(r => r.data),
  remove: (slug: string) => client.delete(`/knowledge-bases/${slug}`),
}
