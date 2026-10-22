import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { authApi, type UserInfo } from '@/api/auth'
import { clearRuntimeCredentials } from '@/security/runtimeCredentials'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const initialized = ref(false)
  const isAuthenticated = computed(() => user.value !== null)

  function clearSession() {
    user.value = null
    clearRuntimeCredentials()
  }

  async function fetchUser() {
    try {
      user.value = await authApi.getMe()
    } catch {
      clearSession()
    } finally {
      initialized.value = true
    }
  }

  async function initialize() {
    if (!initialized.value) {
      await fetchUser()
    }
  }

  async function login(username: string, password: string) {
    const res = await authApi.login({ username, password })
    await fetchUser()
    return res
  }

  async function register(username: string, password: string, email?: string) {
    const res = await authApi.register({ username, password, email })
    await fetchUser()
    return res
  }

  async function logout() {
    try {
      await authApi.logout()
    } finally {
      clearSession()
      initialized.value = true
    }
  }

  return {
    user,
    initialized,
    isAuthenticated,
    initialize,
    login,
    register,
    fetchUser,
    logout,
  }
})
