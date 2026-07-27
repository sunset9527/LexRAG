import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi, type UserInfo } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('lexrag_token') || '')
  const user = ref<UserInfo | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  function setToken(newToken: string) {
    token.value = newToken
    localStorage.setItem('lexrag_token', newToken)
  }

  function clearToken() {
    token.value = ''
    user.value = null
    localStorage.removeItem('lexrag_token')
  }

  async function login(username: string, password: string) {
    const res = await authApi.login({ username, password })
    setToken(res.access_token)
    await fetchUser()
    return res
  }

  async function register(username: string, password: string, email?: string) {
    const res = await authApi.register({ username, password, email })
    setToken(res.access_token)
    await fetchUser()
    return res
  }

  async function fetchUser() {
    if (!token.value) return
    try {
      user.value = await authApi.getMe()
    } catch {
      clearToken()
    }
  }

  function logout() {
    clearToken()
  }

  return {
    token,
    user,
    isAuthenticated,
    setToken,
    clearToken,
    login,
    register,
    fetchUser,
    logout,
  }
})
