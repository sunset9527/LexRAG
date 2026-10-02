import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue'),
      meta: { guest: true },
    },
    {
      path: '/register',
      name: 'Register',
      component: () => import('@/views/Register.vue'),
      meta: { guest: true },
    },
    {
      path: '/',
      component: () => import('@/components/AppLayout.vue'),
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('@/views/Dashboard.vue'),
          meta: { title: '首页' },
        },
        {
          path: 'chat',
          name: 'Chat',
          component: () => import('@/views/Chat.vue'),
          meta: { title: '法律咨询' },
        },
        {
          path: 'chat/:sessionId',
          name: 'ChatSession',
          component: () => import('@/views/Chat.vue'),
          meta: { title: '法律咨询' },
        },
        {
          path: 'search',
          name: 'Search',
          component: () => import('@/views/Search.vue'),
          meta: { title: '法律检索' },
        },
        {
          path: 'graph',
          name: 'Graph',
          component: () => import('@/views/Graph.vue'),
          meta: { title: '知识图谱' },
        },
        {
          path: 'laws',
          name: 'Laws',
          component: () => import('@/views/Laws.vue'),
          meta: { title: '法规浏览' },
        },
        {
          path: 'knowledge-bases',
          name: 'KnowledgeBases',
          component: () => import('@/views/KnowledgeBases.vue'),
          meta: { title: '知识库管理' },
        },
        {
          path: 'documents',
          name: 'Documents',
          component: () => import('@/views/Documents.vue'),
          meta: { title: '文档解析中心' },
        },
        {
          path: 'cases',
          name: 'Cases',
          component: () => import('@/views/Cases.vue'),
          meta: { title: '案例库' },
        },
        {
          path: 'favorites',
          name: 'Favorites',
          component: () => import('@/views/Favorites.vue'),
          meta: { title: '我的收藏' },
        },
        {
          path: 'scenarios',
          name: 'Scenarios',
          component: () => import('@/views/Scenarios.vue'),
          meta: { title: '法律场景' },
        },
        {
          path: 'settings',
          name: 'Settings',
          component: () => import('@/views/Settings.vue'),
          meta: { title: '设置' },
        },
        { path: 'admin', name: 'Admin', component: () => import('@/views/Admin.vue'), meta: { title: '企业管理' } },
      ],
    },
  ],
})

// 路由守卫：未登录跳转登录页
router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()

  if (to.meta.guest) {
    // 已登录用户访问登录/注册页 → 跳转首页
    if (authStore.isAuthenticated) {
      return next('/dashboard')
    }
    return next()
  }

  // 需要认证的页面
  if (!authStore.isAuthenticated) {
    return next('/login')
  }

  next()
})

export default router
