import client from './client'
import type { Citation } from './query'

export interface Favorite {
  id: number
  question: string
  answer: string
  citations: Citation[]
  knowledge_base_slug?: string | null
  law_area?: string | null
  created_at?: string | null
}

export const favoritesApi = {
  create(payload: Omit<Favorite, 'id' | 'created_at'>): Promise<Favorite> {
    return client.post('/favorites', payload).then((response) => response.data)
  },
  list(params?: { law_area?: string; knowledge_base_slug?: string }): Promise<Favorite[]> {
    return client.get('/favorites', { params }).then((response) => response.data.items)
  },
  remove(id: number): Promise<void> {
    return client.delete(`/favorites/${id}`).then(() => undefined)
  },
}
