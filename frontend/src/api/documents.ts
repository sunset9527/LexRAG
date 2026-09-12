import client from './client'
import type { KnowledgeBase } from './knowledgeBases'

export interface DocumentJob {
  id: string
  knowledge_base_slug: string
  original_filename: string
  file_type: 'pdf' | 'docx'
  file_size: number
  status: 'UPLOADED' | 'PARSING' | 'CHUNKING' | 'INDEXING' | 'READY' | 'FAILED'
  progress: number
  chunk_size: number
  chunk_overlap: number
  page_count: number | null
  character_count: number | null
  chunk_count: number | null
  error_message: string | null
}

export const documentApi = {
  createLibrary: (data: { name: string; slug: string; law_area: string }) => client.post<KnowledgeBase>('/document-libraries', data).then(r => r.data),
  list: (slug: string) => client.get<{ items: DocumentJob[] }>(`/document-libraries/${slug}/documents`).then(r => r.data.items),
  upload: (slug: string, file: File, chunkSize: number, chunkOverlap: number) => {
    const form = new FormData()
    form.append('file', file)
    form.append('chunk_size', String(chunkSize))
    form.append('chunk_overlap', String(chunkOverlap))
    return client.post<DocumentJob>(`/document-libraries/${slug}/documents`, form, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data)
  },
  retry: (id: string) => client.post<DocumentJob>(`/documents/${id}/retry`).then(r => r.data),
}
