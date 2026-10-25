import client from './client'

export interface CaseSource { id: number; title: string; domain: string; page_count: number; processed_pages: number; status: string; origin_label: string }
export interface LegalCase { id: string; source_id: number; sequence_no: number; title: string | null; domain: string; case_cause: string; case_number?: string | null; court_name?: string | null; judgment_date?: string | null; key_facts: string; issues: string | null; court_reasoning: string | null; judgment_result: string | null; judge_commentary: string | null; legal_basis: string[]; source_start_page: number; source_end_page: number; extraction_warnings: string[]; metadata_complete: boolean; missing_fields: string[] }

export const caseApi = {
  sources: (domain?: string) => client.get<{ items: CaseSource[] }>('/case-sources', { params: { domain: domain || undefined } }).then(r => r.data.items),
  list: (params: { domain?: string; case_cause?: string; source_id?: number }) => client.get<{ items: LegalCase[] }>('/cases', { params }).then(r => r.data.items),
  detail: (id: string) => client.get<LegalCase>(`/cases/${id}`).then(r => r.data),
  similar: (id: string) => client.get<{ items: Array<LegalCase & { similarity_score: number; case_cause_match: boolean }> }>(`/cases/${id}/similar`).then(r => r.data.items),
}
