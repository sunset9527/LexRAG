<template>
  <div class="laws-page">
    <el-row :gutter="20" style="height: 100%;">
      <!-- 左侧目录树 -->
      <el-col :span="7">
        <el-card shadow="never" class="law-tree-card">
          <template #header>
            <span style="font-weight: 600;">📚 法规目录</span>
          </template>
          <el-tree
            :data="lawTree"
            :props="{ children: 'children', label: 'label' }"
            node-key="id"
            :default-expanded-keys="['民法典']"
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
                📖 {{ currentLaw || '请选择法律' }}
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
import { ref, computed } from 'vue'

interface ArticleData {
  id: string
  content: string
  references?: string[]
}

const currentLaw = ref('民法典·合同编')
const articleSearch = ref('')

// 示例数据（v1.9 法律数据基建完成后接入真实 API）
const mockArticles = ref<ArticleData[]>([
  { id: '民法典第463条', content: '本编调整因合同产生的民事关系。' },
  { id: '民法典第464条', content: '合同是民事主体之间设立、变更、终止民事法律关系的协议。婚姻、收养、监护等有关身份关系的协议，适用有关该身份关系的法律规定；没有规定的，可以根据其性质参照适用本编规定。' },
  { id: '民法典第465条', content: '依法成立的合同，受法律保护。依法成立的合同，仅对当事人具有法律约束力，但是法律另有规定的除外。' },
  { id: '民法典第466条', content: '当事人对合同条款的理解有争议的，应当依据本法第一百四十二条第一款的规定，确定争议条款的含义。合同文本采用两种以上文字订立并约定具有同等效力的，对各文本使用的词句推定具有相同含义。各文本使用的词句不一致的，应当根据合同的相关条款、性质、目的以及诚信原则等予以解释。' },
  { id: '民法典第467条', content: '本法或者其他法律没有明文规定的合同，适用本编通则的规定，并可以参照适用本编或者其他法律最相类似合同的规定。' },
  { id: '民法典第470条', content: '合同的内容由当事人约定，一般包括下列条款：（一）当事人的姓名或者名称和住所；（二）标的；（三）数量；（四）质量；（五）价款或者报酬；（六）履行期限、地点和方式；（七）违约责任；（八）解决争议的方法。当事人可以参照各类合同的示范文本订立合同。' },
])

const lawTree = [
  {
    id: '民法典',
    label: '中华人民共和国民法典',
    children: [
      { id: '总则编', label: '总则编', count: 204 },
      { id: '物权编', label: '物权编', count: 258 },
      { id: '合同编', label: '合同编', count: 526, children: [
        { id: '合同编-通则', label: '通则', count: 132 },
        { id: '合同编-典型合同', label: '典型合同', count: 384 },
        { id: '合同编-准合同', label: '准合同', count: 10 },
      ]},
      { id: '人格权编', label: '人格权编', count: 51 },
      { id: '婚姻家庭编', label: '婚姻家庭编', count: 79 },
      { id: '继承编', label: '继承编', count: 45 },
      { id: '侵权责任编', label: '侵权责任编', count: 97 },
    ],
  },
]

const filteredArticles = computed(() => {
  if (!articleSearch.value) return mockArticles.value
  const num = articleSearch.value.replace(/[^0-9]/g, '')
  if (!num) return mockArticles.value
  return mockArticles.value.filter((a) => a.id.includes(num))
})

function handleNodeClick(data: any) {
  if (data.id && !data.children) {
    currentLaw.value = data.label || data.id
  }
}
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
