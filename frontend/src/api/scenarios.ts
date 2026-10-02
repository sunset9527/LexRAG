import client from './client'

export type ScenarioType = 'contract_review' | 'compliance_check' | 'document_draft' | 'rights_path'
export interface ScenarioResult { evidence_status?: string; citations?: string[]; findings?: Array<Record<string, any>>; path?: Array<Record<string, string>>; content?: string; disclaimer?: string; [key: string]: unknown }
export interface ScenarioJob { id: string; scenario_type: ScenarioType; input_data: Record<string, unknown>; result_data?: ScenarioResult; status: 'PENDING' | 'PROCESSING' | 'READY' | 'FAILED'; error_message?: string }

export const scenarioApi = {
  create: (scenario_type: ScenarioType, input_data: Record<string, unknown>) => client.post<ScenarioJob>('/scenarios', { scenario_type, input_data }).then(r => r.data),
  uploadContract: (file: File) => { const form = new FormData(); form.append('file', file); return client.post<ScenarioJob>('/scenarios/contract-file', form).then(r => r.data) },
  list: () => client.get<{ items: ScenarioJob[] }>('/scenarios').then(r => r.data.items),
  get: (id: string) => client.get<ScenarioJob>(`/scenarios/${id}`).then(r => r.data),
  retry: (id: string) => client.post(`/scenarios/${id}/retry`).then(r => r.data),
  generateAdvice: (id: string) => client.post<ScenarioJob>(`/scenarios/${id}/advice`).then(r => r.data),
  reportUrl: (id: string) => `/api/scenarios/${id}/report.pdf`,
}
