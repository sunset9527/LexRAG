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

export interface DocumentPageResult {
  page_number: number
  raw_text: string
  search_text: string
  source: 'text' | 'ocr' | 'empty' | 'docx'
  ocr_confidence: number | null
  tables: Array<{ rows: Array<Array<string | null>>; bbox: number[]; method: string }>
  header: string | null
  footer: string | null
  parse_warnings: string[]
}

export interface DocumentResult {
  id: string
  knowledge_base_slug: string
  original_filename: string
  file_type: 'pdf' | 'docx'
  status: DocumentJob['status']
  page_count: number
  table_count: number
  relations_count: number
  structure: {
    document_type: string
    content: Record<string, unknown>
    parser_version: string
    status: string
    error_message: string | null
  } | null
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
  uploadBatch: (slug: string, files: File[], chunkSize: number, chunkOverlap: number) => {
    const form = new FormData()
    files.forEach(file => form.append('files', file))
    form.append('chunk_size', String(chunkSize))
    form.append('chunk_overlap', String(chunkOverlap))
    return client.post<{ items: Array<{ original_filename: string; job?: DocumentJob; error?: string }> }>(`/document-libraries/${slug}/documents/batch`, form, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data)
  },
  retry: (id: string) => client.post<DocumentJob>(`/documents/${id}/retry`).then(r => r.data),
  result: (id: string) => client.get<DocumentResult>(`/documents/${id}/result`).then(r => r.data),
  pages: (id: string, page = 1, pageSize = 20) => client.get<{ total: number; page: number; page_size: number; items: DocumentPageResult[] }>(`/documents/${id}/pages`, { params: { page, page_size: pageSize } }).then(r => r.data),
}
