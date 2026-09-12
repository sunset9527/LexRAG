<template>
  <div class="search-page">
    <!-- 搜索框 -->
    <div class="search-hero">
      <h2 class="search-title">法律检索</h2>
      <p class="search-subtitle">搜索法条、案例、司法解释，获得结构化法律信息</p>
      <el-select v-model="knowledgeBaseId" placeholder="选择知识库" aria-label="选择检索知识库" class="knowledge-base-select">
        <el-option v-for="item in knowledgeBases" :key="item.slug" :label="item.name" :value="item.slug" />
      </el-select>
      <el-input
        v-model="query"
        size="large"
        placeholder="输入法律关键词，如「劳动合同解除 赔偿」…"
        clearable
        @keyup.enter="handleSearch"
        class="search-input"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
        <template #append>
          <el-button type="primary" :loading="loading" @click="handleSearch">
            检索
          </el-button>
        </template>
      </el-input>
    </div>

    <!-- 搜索结果 -->
    <div v-if="results.length > 0" class="results-section">
      <div class="results-header">
        <span>找到 {{ results.length }} 条结果</span>
        <el-radio-group v-model="filter" size="small">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="statute">法条</el-radio-button>
          <el-radio-button value="case">案例</el-radio-button>
          <el-radio-button value="analysis">分析</el-radio-button>
        </el-radio-group>
      </div>

      <div class="result-list">
        <div v-for="(r, i) in filteredResults" :key="i" class="result-card">
          <div class="result-type">
            <el-tag
              :type="r.type === 'statute' ? 'primary' : r.type === 'case' ? 'success' : 'info'"
              size="small"
            >
              {{ r.type === 'statute' ? '法条' : r.type === 'case' ? '案例' : '分析' }}
            </el-tag>
          </div>
          <h3 class="result-title">{{ r.title }}</h3>
          <p class="result-snippet" v-html="r.snippet" />
          <div class="result-meta">
            <span v-if="r.law">{{ r.law }}</span>
            <span v-if="r.date">{{ r.date }}</span>
            <span v-if="r.court">{{ r.court }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="searched" class="empty-results">
      <el-icon :size="48" color="#c0c4cc"><Document /></el-icon>
      <p>未找到相关结果</p>
      <p class="empty-hint">试试更换关键词或使用更精确的法律术语</p>
    </div>

    <!-- 热门搜索 -->
    <div v-if="!searched" class="hot-searches">
      <h3>🔥 热门检索</h3>
      <el-row :gutter="12">
        <el-col :span="8" v-for="kw in hotKeywords" :key="kw">
          <el-button class="hot-kw-btn" @click="query = kw; handleSearch()">
            {{ kw }}
          </el-button>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { knowledgeBaseApi, type KnowledgeBase } from '@/api/knowledgeBases'

interface SearchResult {
  type: 'statute' | 'case' | 'analysis'
  title: string
  snippet: string
  law?: string
  date?: string
  court?: string
}

const query = ref('')
const loading = ref(false)
const searched = ref(false)
const filter = ref('all')
const results = ref<SearchResult[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const knowledgeBaseId = ref('')

const hotKeywords = [
  '劳动合同解除', '违约金', '消费者权益',
  '交通事故赔偿', '离婚财产分割', '继承纠纷',
  '民间借贷', '房屋买卖', '知识产权',
]

const filteredResults = computed(() => {
  if (filter.value === 'all') return results.value
  return results.value.filter((r) => r.type === filter.value)
})

async function handleSearch() {
  const q = query.value.trim()
  if (!q) return

  loading.value = true
  searched.value = true

  try {
    // 调用后端 query API（复用问答接口的结果展示为检索）
    const { queryApi } = await import('@/api/query')
    const res = await queryApi.ask({ query: q, knowledge_base_ids: knowledgeBaseId.value ? [knowledgeBaseId.value] : undefined })

    results.value = []

    // 引用的法条
    if (res.citations?.length) {
      res.citations.forEach((c) => {
        results.value.push({
          type: 'statute',
          title: c.article_id,
          snippet: c.original_text || c.citation_text,
          law: '民法典',
          is_verified: c.is_verified,
        } as any)
      })
    }

    // 回答本身作为分析
    if (res.answer) {
      results.value.push({
        type: 'analysis',
        title: q,
        snippet: res.answer.slice(0, 300) + (res.answer.length > 300 ? '…' : ''),
      } as any)
    }
  } catch {
    // 搜索失败静默处理
  } finally {
    loading.value = false
  }
}

onMounted(() => knowledgeBaseApi.list().then(items => {
  knowledgeBases.value = items.filter(item => item.status === 'READY')
  knowledgeBaseId.value = knowledgeBases.value[0]?.slug || ''
}))
</script>

<style scoped>
.search-page { max-width: 900px; margin: 0 auto; }

.search-hero {
  text-align: center;
  padding: 32px 0 24px;
}

.search-title {
  font-family: 'Noto Serif SC', STSong, serif;
  font-size: 28px;
  color: #0f1f3d;
  margin: 0 0 8px;
}

.search-subtitle { color: #909399; margin-bottom: 20px; }

.search-input { max-width: 700px; margin: 0 auto; }
.knowledge-base-select { width: 240px; margin-bottom: 12px; }

.results-section { margin-top: 24px; }

.results-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px; font-size: 14px; color: #909399;
}

.result-card {
  background: #fff; padding: 20px; margin-bottom: 12px;
  border-radius: 10px; border: 1px solid #ebeef5;
  transition: box-shadow 0.15s;
}
.result-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.08); }

.result-type { margin-bottom: 8px; }

.result-title {
  font-size: 16px; color: #0f1f3d; margin: 0 0 8px;
}

.result-snippet {
  font-size: 14px; color: #606266; line-height: 1.7;
}

.result-meta {
  margin-top: 10px; font-size: 12px; color: #c0c4cc;
  display: flex; gap: 16px;
}

.empty-results { text-align: center; padding: 60px 0; color: #c0c4cc; }
.empty-hint { font-size: 13px; margin-top: 8px; }

.hot-searches { margin-top: 32px; }
.hot-searches h3 { font-size: 16px; color: #303133; margin-bottom: 12px; }
.hot-kw-btn { width: 100%; margin-bottom: 8px; }
</style>
