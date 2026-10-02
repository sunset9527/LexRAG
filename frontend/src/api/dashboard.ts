import client from './client'

export interface DashboardStats {
  case_count: number
  source_count: number
}

export const dashboardApi = {
  stats: (): Promise<DashboardStats> => client.get('/dashboard/stats').then((response) => response.data),
}
