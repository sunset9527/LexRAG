<template>
  <div class="dashboard">
    <!-- 欢迎区域 -->
    <div class="hero-section">
      <h1 class="hero-title">法律智能知识平台</h1>
      <p class="hero-subtitle">基于 RAG + Multi-Agent + 法条自校验，为您提供准确、可溯源的法律咨询</p>
      <div class="hero-actions">
        <el-button type="primary" size="large" @click="$router.push('/chat')">
          <el-icon><ChatDotRound /></el-icon> 开始法律咨询
        </el-button>
        <el-button size="large" @click="$router.push('/search')">
          <el-icon><Search /></el-icon> 法律检索
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" style="background: #e8f0fe;">
            <el-icon :size="28" color="#2d5cc5"><Document /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.lawCount }}</div>
            <div class="stat-label">收录法条</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" style="background: #e6f7ed;">
            <el-icon :size="28" color="#27ae60"><Files /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.caseCount }}</div>
            <div class="stat-label">参考案例</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" style="background: #fdf6ec;">
            <el-icon :size="28" color="#c9a84c"><Checked /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.verifyRate }}%</div>
            <div class="stat-label">法条校验率</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" style="background: #fde8e8;">
            <el-icon :size="28" color="#c0392b"><Star /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.queryCount }}</div>
            <div class="stat-label">今日咨询</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 双栏布局 -->
    <el-row :gutter="20" class="content-row">
      <!-- 热门法律问题 -->
      <el-col :span="14">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="card-header">
              <span>🔥 热门法律问题</span>
              <el-tag size="small" type="info">民法典</el-tag>
            </div>
          </template>
          <div class="hot-questions">
            <div
              v-for="q in hotQuestions"
              :key="q"
              class="hot-item"
              @click="goToChat(q)"
            >
              <el-icon color="#2d5cc5"><ArrowRight /></el-icon>
              <span>{{ q }}</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 最近查询 & 知识库 -->
      <el-col :span="10">
        <el-card shadow="never" class="section-card">
          <template #header>
            <span>📋 知识库覆盖</span>
          </template>
          <div class="kb-list">
            <div v-for="kb in knowledgeBases" :key="kb.name" class="kb-item">
              <span class="kb-name">{{ kb.name }}</span>
              <el-progress
                :percentage="kb.coverage"
                :stroke-width="8"
                :color="kb.coverage >= 80 ? '#27ae60' : kb.coverage >= 40 ? '#2d5cc5' : '#c9a84c'"
              />
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const stats = reactive({
  lawCount: '39',
  caseCount: '0',
  verifyRate: '100',
  queryCount: '--',
})

const hotQuestions = [
  '合同成立需要满足哪些条件？',
  '格式条款什么情况下无效？',
  '定金和订金有什么区别？',
  '什么情况下可以解除合同？',
  '违约责任如何计算赔偿金额？',
  '借款合同没有约定利息怎么办？',
]

const knowledgeBases = [
  { name: '民法典·合同编', coverage: 100 },
  { name: '民法典·总则编', coverage: 0 },
  { name: '民法典·物权编', coverage: 0 },
  { name: '劳动法', coverage: 0 },
  { name: '公司法', coverage: 0 },
]

function goToChat(question: string) {
  router.push({ path: '/chat', query: { q: question } })
}
</script>

<style scoped>
.dashboard { max-width: 1200px; margin: 0 auto; }

.hero-section {
  text-align: center;
  padding: 40px 0 32px;
}

.hero-title {
  font-family: 'Noto Serif SC', STSong, serif;
  font-size: 36px;
  font-weight: 700;
  color: #0f1f3d;
  margin: 0 0 12px;
}

.hero-subtitle {
  color: #606266;
  font-size: 15px;
  margin-bottom: 24px;
}

.hero-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.stats-row { margin-bottom: 24px; }

.stat-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  cursor: default;
  transition: box-shadow 0.2s;
}
.stat-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }

.stat-icon {
  width: 56px; height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-value { font-size: 24px; font-weight: 700; color: #0f1f3d; }
.stat-label { font-size: 13px; color: #909399; margin-top: 2px; }

.content-row { margin-bottom: 24px; }

.section-card {
  border-radius: 12px;
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.hot-questions { display: flex; flex-direction: column; gap: 2px; }

.hot-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  font-size: 14px;
  color: #303133;
}
.hot-item:hover { background: #e8f0fe; }

.kb-list { display: flex; flex-direction: column; gap: 16px; }

.kb-item { display: flex; flex-direction: column; gap: 6px; }

.kb-name { font-size: 14px; color: #303133; font-weight: 500; }
</style>
