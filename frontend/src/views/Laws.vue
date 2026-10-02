<template>
  <div class="laws-page">
    <el-row :gutter="20" style="height: 100%;">
      <!-- 左侧目录树 -->
      <el-col :span="7">
        <el-card shadow="never" class="law-tree-card">
          <template #header>
            <span style="font-weight: 600;"><el-icon><Reading /></el-icon> 法规目录</span>
          </template>
          <el-tree
            :data="lawTree"
            :props="{ children: 'children', label: 'label' }"
            node-key="id"
            highlight-current
            @node-click="handleNodeClick"
          >
            <template #default="{ data }">
              <span class="tree-node">
                <span>{{ data.label }}</span>
                <el-tag v-if="data.count" size="small" type="info" class="tree-count">
                  {{ data.count }}条
                </el-tag>
              </span>
            </template>
          </el-tree>
        </el-card>
      </el-col>

      <!-- 右侧法条内容 -->
      <el-col :span="17">
        <el-card shadow="never" class="law-content-card">
          <template #header>
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <span style="font-weight: 600;">
                <el-icon><Document /></el-icon> {{ currentLaw || '请选择法律' }}
              </span>
              <el-input
                v-model="articleSearch"
                placeholder="输入条号快速定位…"
                size="small"
                clearable
                style="width: 220px"
              />
            </div>
          </template>

          <div v-if="!currentLaw" class="empty-content">
            <el-icon :size="48" color="#c0c4cc"><Reading /></el-icon>
            <p>请从左侧目录选择法律浏览</p>
          </div>

          <div v-else class="articles-list">
            <div
              v-for="article in filteredArticles"
              :key="article.id"
              class="article-item"
            >
              <div class="article-header">
                <h4 class="article-title">{{ article.id }}</h4>
              </div>
              <p class="article-content">{{ article.content }}</p>
              <div v-if="article.references?.length" class="article-refs">
                <span class="ref-label">引用法条：</span>
                <el-tag
                  v-for="ref in article.references"
                  :key="ref"
                  size="small"
                  type="info"
                  class="ref-tag"
                >
                  {{ ref }}
                </el-tag>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { knowledgeBaseApi } from '@/api/knowledgeBases'
import { buildStatuteTree } from '@/utils/lawPresentation'

interface ArticleData {
  id: string
  article_number?: number | string
  content: string
  references?: string[]
}

const currentLaw = ref('')
const articleSearch = ref('')
const currentKnowledgeBaseSlug = ref('')

const mockArticles = ref<ArticleData[]>([])

const lawTree = ref<any[]>([])

const filteredArticles = computed(() => {
  if (!articleSearch.value) return mockArticles.value
  const num = articleSearch.value.replace(/[^0-9]/g, '')
  if (!num) return mockArticles.value
  return mockArticles.value.filter((a) => a.id.includes(num))
})

function handleNodeClick(data: any) {
  const slug = data.knowledgeBaseSlug || data.slug
  if (!slug) return
  currentKnowledgeBaseSlug.value = slug
  articleSearch.value = ''
  currentLaw.value = data.lawName || data.label || data.id
  if (data.startArticle && data.endArticle) {
    loadArticles({ startArticle: data.startArticle, endArticle: data.endArticle })
  } else {
    loadArticles()
  }
}

async function loadArticles(range?: { startArticle: number; endArticle: number }) {
  mockArticles.value = await knowledgeBaseApi.laws(currentKnowledgeBaseSlug.value, range)
}

onMounted(async () => {
  const knowledgeBases = await knowledgeBaseApi.list()
  lawTree.value = buildStatuteTree(knowledgeBases)
  const selected = knowledgeBases.find(item => item.type === 'statute' && item.status === 'READY')
  if (!selected) return
  currentLaw.value = selected.name
  currentKnowledgeBaseSlug.value = selected.slug
  await loadArticles()
})
</script>

<style scoped>
.laws-page { height: calc(100vh - 48px); }

.law-tree-card, .law-content-card {
  height: 100%;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
}
.law-tree-card :deep(.el-card__body), .law-content-card :deep(.el-card__body) {
  flex: 1;
  overflow-y: auto;
}

.tree-node { display: flex; align-items: center; justify-content: space-between; flex: 1; }
.tree-count { margin-left: 8px; }

.empty-content {
  text-align: center; padding: 60px 0; color: #c0c4cc;
}

.articles-list {
  display: flex; flex-direction: column; gap: 0;
}

.article-item {
  padding: 16px 0;
  border-bottom: 1px solid #f0f0f0;
}

.article-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }

.article-title {
  font-family: 'Noto Serif SC', STSong, serif;
  font-size: 15px; color: #1a3a7f; margin: 0;
}

.article-content {
  font-size: 14px; color: #303133; line-height: 1.9; margin: 0;
}

.article-refs { margin-top: 8px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.ref-label { font-size: 12px; color: #909399; }
.ref-tag { cursor: pointer; }
</style>
