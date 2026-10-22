/**
 * Axios 封装 — HttpOnly 会话 Cookie + 内存 BYOK / 模型配置 header
 */
import axios from 'axios'
import type { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { getRuntimeApiKey } from '@/security/runtimeCredentials'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

const client: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  timeout: 120000, // 法律问答可能较慢
  headers: { 'Content-Type': 'application/json' },
})

// ========== 请求拦截器 ==========
client.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // 用户自定义 API Key 仅保存在当前页面内存。
    const apiKey = getRuntimeApiKey()
    if (apiKey && config.headers) {
      config.headers['X-API-Key'] = apiKey
    }

    // 用户选择的模型
    const model = localStorage.getItem('lexrag_model')
    if (model && config.headers) {
      config.headers['X-Model'] = model
    }

    // 用户自定义的 API Base URL
    const baseUrl = localStorage.getItem('lexrag_base_url')
    if (baseUrl && config.headers) {
      config.headers['X-Base-URL'] = baseUrl
    }

    return config
  },
  (error: AxiosError) => Promise.reject(error),
)

// ========== 响应拦截器 ==========
client.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // 不在登录页才跳转
      if (router.currentRoute.value.path !== '/login') {
        router.push('/login')
        ElMessage.warning('登录已过期，请重新登录')
      }
    } else if (error.response?.status === 503) {
      ElMessage.error('服务不可用，请稍后重试')
    } else if (!error.response) {
      ElMessage.error('网络连接失败，请检查网络')
    }
    return Promise.reject(error)
  },
)

export default client
