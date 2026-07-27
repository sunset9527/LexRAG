<template>
  <el-container class="app-container">
    <!-- 侧边导航 -->
    <el-aside width="220px" class="sidebar">
      <div class="logo-section">
        <span class="logo-icon">⚖️</span>
        <span class="logo-text">LexRAG</span>
      </div>

      <el-menu
        :default-active="currentRoute"
        router
        background-color="transparent"
        text-color="#c5d9fa"
        active-text-color="#ffffff"
        class="nav-menu"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>法律咨询</span>
        </el-menu-item>
        <el-menu-item index="/search">
          <el-icon><Search /></el-icon>
          <span>法律检索</span>
        </el-menu-item>
        <el-menu-item index="/graph">
          <el-icon><Connection /></el-icon>
          <span>知识图谱</span>
        </el-menu-item>
        <el-menu-item index="/laws">
          <el-icon><Reading /></el-icon>
          <span>法规浏览</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>设置</span>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-footer">
        <div class="user-info">
          <el-avatar :size="32" icon="UserFilled" />
          <span class="username">{{ authStore.user?.username || '用户' }}</span>
        </div>
        <el-button text size="small" @click="handleLogout" class="logout-btn">
          <el-icon><SwitchButton /></el-icon>
        </el-button>
      </div>
    </el-aside>

    <!-- 主内容区 -->
    <el-main class="main-content">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const currentRoute = computed(() => route.path)

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.app-container {
  height: 100vh;
}

.sidebar {
  background: linear-gradient(180deg, #0a1628 0%, #0f1f3d 50%, #152d5e 100%);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.logo-section {
  padding: 20px 20px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.logo-icon {
  font-size: 28px;
}

.logo-text {
  font-family: 'Noto Serif SC', STSong, serif;
  font-size: 22px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 2px;
}

.nav-menu {
  flex: 1;
  padding-top: 12px;
}

.nav-menu .el-menu-item {
  margin: 4px 12px;
  border-radius: 8px;
  height: 44px;
  line-height: 44px;
}

.nav-menu .el-menu-item:hover {
  background: rgba(255, 255, 255, 0.08) !important;
}

.nav-menu .el-menu-item.is-active {
  background: rgba(255, 255, 255, 0.15) !important;
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.username {
  color: #c5d9fa;
  font-size: 14px;
}

.logout-btn {
  color: #8aaff5;
}

.main-content {
  background: #f5f7fa;
  padding: 24px;
  overflow-y: auto;
  height: 100vh;
}
</style>
