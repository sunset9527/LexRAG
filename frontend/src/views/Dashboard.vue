<template>
  <div class="dashboard">
    <!-- 欢迎区域 -->
    <div class="hero-section">
      <div class="eyebrow">LEXRAG · LEGAL RESEARCH</div>
      <h1 class="hero-title">法律研究工作台</h1>
      <p class="hero-subtitle">基于已收录法规、可核验法条和真实案例数据开展研究与咨询。</p>
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
          <div class="stat-icon info">
            <el-icon :size="22"><Document /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.lawCount }}</div>
            <div class="stat-label">收录法条</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon success">
            <el-icon :size="22"><Files /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.caseCount }}</div>
            <div class="stat-label">参考案例</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon info">
            <el-icon :size="22"><Checked /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.verifyRate }}%</div>
            <div class="stat-label">法条校验率</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon neutral">
            <el-icon :size="22"><Star /></el-icon>
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
              <span>常见法律问题</span>
              <el-select v-model="selectedQuestionLawSlug" size="small" aria-label="选择常见问题的法规库" style="width: 210px">
                <el-option v-for="item in statuteKnowledgeBases" :key="item.slug" :label="item.name" :value="item.slug" />
              </el-select>
            </div>
          </template>
          <div class="hot-questions">
            <div
              v-for="q in hotQuestions"
              :key="q"
              class="hot-item"
              @click="goToChat(q, selectedQuestionLawSlug)"
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
          <template #header><span>知识库覆盖</span></template>
          <div class="kb-list">
            <div v-for="kb in knowledgeBases" :key="kb.name" class="kb-item">
              <span class="kb-name">{{ kb.name }}（{{ kb.status === 'READY' ? '可用' : kb.status === 'INDEXING' ? '索引中' : '待索引' }}）</span>
              <el-progress
                :percentage="kb.status === 'READY' ? 100 : 0"
                :stroke-width="8"
                :color="kb.status === 'READY' ? '#27ae60' : '#c9a84c'"
              />
              <small>{{ kb.document_count }} 条 · {{ kb.chunk_count }} chunks</small>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { knowledgeBaseApi, type KnowledgeBase } from '@/api/knowledgeBases'
import { getQuestionPresets } from '@/utils/lawPresentation'
import { dashboardApi } from '@/api/dashboard'

const router = useRouter()

const stats = reactive({
  lawCount: '—',
  caseCount: '0',
  verifyRate: '100',
  queryCount: '--',
})

const knowledgeBases = ref<KnowledgeBase[]>([])
const selectedQuestionLawSlug = ref('')
const statuteKnowledgeBases = computed(() => knowledgeBases.value.filter(
  item => item.type === 'statute' && item.status === 'READY',
))
const hotQuestions = computed(() => getQuestionPresets(selectedQuestionLawSlug.value))

onMounted(async () => {
  try {
    knowledgeBases.value = await knowledgeBaseApi.list()
    selectedQuestionLawSlug.value = statuteKnowledgeBases.value[0]?.slug || ''
    stats.lawCount = String(
      knowledgeBases.value
        .filter(item => item.status === 'READY')
        .reduce((total, item) => total + item.document_count, 0),
    )
  } catch {
    stats.lawCount = '加载失败'
  }
  try {
    const dashboardStats = await dashboardApi.stats()
    stats.caseCount = String(dashboardStats.case_count)
  } catch {
    stats.caseCount = '加载失败'
  }
})

function goToChat(question: string, knowledgeBaseSlug: string) {
  router.push({ path: '/chat', query: { q: question, kb: knowledgeBaseSlug } })
}
</script>

<style scoped>
.dashboard { max-width: 1360px; margin: 0 auto; }

.hero-section {
  padding: 20px 0 28px;
}

.hero-title {
  font-size: 28px;
  font-weight: 650;
  color: var(--text-primary);
  margin: 4px 0 8px;
}

.hero-subtitle {
  color: var(--text-secondary);
  margin: 0 0 20px;
}

.eyebrow { color: var(--brand-primary); font-size: 11px; font-weight: 700; letter-spacing: .1em; }

.hero-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.stats-row { margin-bottom: 20px; }

.stat-card {
  background: #fff;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 18px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: none;
  cursor: default;
  transition: box-shadow 0.2s;
}
.stat-card:hover { border-color: var(--border-strong); box-shadow: var(--shadow-panel); }

.stat-icon {
  width: 40px; height: 40px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-icon.info { color: var(--brand-primary); background: var(--surface-selected); }
.stat-icon.success { color: var(--status-success); background: #f0fdf4; }
.stat-icon.neutral { color: var(--text-secondary); background: var(--surface-subtle); }
.stat-value { font-size: 22px; font-weight: 700; color: var(--text-primary); font-variant-numeric: tabular-nums; }
.stat-label { font-size: 13px; color: var(--text-secondary); margin-top: 2px; }

.content-row { margin-bottom: 24px; }

.section-card { border-radius: var(--radius-md); height: 100%; }

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
  padding: 12px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s;
  font-size: 14px;
  color: var(--text-primary);
}
.hot-item:hover { background: var(--surface-selected); }

.kb-list { display: flex; flex-direction: column; gap: 16px; }

.kb-item { display: flex; flex-direction: column; gap: 6px; }

.kb-name { font-size: 14px; color: var(--text-primary); font-weight: 500; }

@media (max-width: 900px) { .stats-row :deep(.el-col), .content-row :deep(.el-col) { width: 100%; max-width: 100%; flex: 0 0 100%; margin-bottom: 12px; } }
</style>
