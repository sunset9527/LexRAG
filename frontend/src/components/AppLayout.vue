<template>
  <el-container class="app-container">
    <!-- 侧边导航 -->
    <el-aside width="232px" class="sidebar">
      <div class="logo-section">
        <span class="logo-text">LexRAG</span>
        <span class="brand-caption">法律研究</span>
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
        <el-menu-item index="/knowledge-bases">
          <el-icon><Collection /></el-icon>
          <span>知识库管理</span>
        </el-menu-item>
        <el-menu-item index="/documents">
          <el-icon><Files /></el-icon>
          <span>文档解析中心</span>
        </el-menu-item>
        <el-menu-item index="/cases">
          <el-icon><Files /></el-icon>
          <span>案例库</span>
        </el-menu-item>
        <el-menu-item index="/favorites">
          <el-icon><Star /></el-icon>
          <span>我的收藏</span>
        </el-menu-item>
        <el-menu-item index="/scenarios">
          <el-icon><DocumentChecked /></el-icon>
          <span>法律场景</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>设置</span>
        </el-menu-item>
        <el-menu-item index="/admin">
          <el-icon><Setting /></el-icon><span>企业管理</span>
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

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.app-container {
  min-height: 100vh;
  background: var(--surface-canvas);
}

.sidebar {
  background: var(--surface-raised);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.logo-section {
  min-height: 72px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.logo-text {
  font-family: var(--font-display);
  font-size: 21px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: .02em;
}

.brand-caption {
  color: var(--text-tertiary);
  font-size: 12px;
  white-space: nowrap;
}

.nav-menu {
  flex: 1;
  padding: 14px 10px;
  overflow-y: auto;
}

.nav-menu .el-menu-item {
  position: relative;
  margin: 2px 0;
  border-radius: var(--radius-sm);
  height: 42px;
  line-height: 42px;
  color: var(--text-secondary) !important;
  transition: background-color 180ms ease, color 180ms ease;
}

.nav-menu .el-menu-item:hover {
  background: var(--surface-subtle) !important;
  color: var(--text-primary) !important;
}

.nav-menu .el-menu-item.is-active {
  background: var(--surface-selected) !important;
  color: var(--brand-primary) !important;
  font-weight: 600;
}

.nav-menu .el-menu-item.is-active::before {
  content: '';
  position: absolute;
  left: -10px;
  top: 9px;
  bottom: 9px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--brand-primary);
}

.sidebar-footer {
  padding: 14px 16px;
  border-top: 1px solid var(--border-subtle);
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
  color: var(--text-secondary);
  font-size: 14px;
}

.logout-btn {
  color: var(--text-tertiary);
}

.main-content {
  background: var(--surface-canvas);
  padding: 24px;
  overflow-y: auto;
  min-height: 100vh;
}

@media (max-width: 1080px) {
  .sidebar { width: 72px !important; }
  .logo-section { justify-content: center; padding: 0; }
  .brand-caption, .logo-text, .nav-menu :deep(.el-menu-item span), .username { display: none; }
  .nav-menu .el-menu-item { justify-content: center; padding: 0 !important; }
  .sidebar-footer { justify-content: center; padding: 14px 0; }
  .main-content { padding: 16px; }
}
</style>
