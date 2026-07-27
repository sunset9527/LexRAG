/**
 * 认证 API
 */
import client from './client'

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  password: string
  email?: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  username: string
  user_id: number
}

export interface UserInfo {
  id: number
  username: string
  email: string | null
  is_active: boolean
  is_superuser: boolean
}

export const authApi = {
  login(data: LoginRequest): Promise<TokenResponse> {
    return client.post('/auth/login', data).then((r) => r.data)
  },

  register(data: RegisterRequest): Promise<TokenResponse> {
    return client.post('/auth/register', data).then((r) => r.data)
  },

  getMe(): Promise<UserInfo> {
    return client.get('/auth/me').then((r) => r.data)
  },
}
