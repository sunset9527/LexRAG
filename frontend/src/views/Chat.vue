<template>
  <div class="chat-page">
    <!-- 双栏布局 -->
    <div class="chat-layout">
      <aside class="session-panel">
        <div class="session-header"><strong>会话</strong><el-button type="primary" size="small" @click="newSession">新建</el-button></div>
        <el-input v-model="sessionQuery" size="small" clearable placeholder="搜索历史对话" @input="searchSessions" />
        <div class="session-list">
          <div v-for="session in store.sessions" :key="session.id" :class="['session-item', { active: session.id === store.currentSessionId }]" @click="openSession(session.id)">
            <span class="session-title">{{ session.title }}</span>
            <el-dropdown trigger="click" @command="(command: string) => handleSessionCommand(command, session.id)"><el-button text size="small" @click.stop>•••</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item command="rename">重命名</el-dropdown-item><el-dropdown-item command="archive" divided>归档</el-dropdown-item></el-dropdown-menu></template></el-dropdown>
          </div>
          <el-empty v-if="!store.sessions.length" description="暂无历史会话" :image-size="56" />
        </div>
      </aside>
      <!-- 左栏：对话区 -->
      <div class="chat-panel">
        <div class="panel-header"><el-icon><ChatDotRound /></el-icon><span>法律咨询</span>
          <el-select v-model="knowledgeBaseId" size="small" aria-label="选择检索知识库" style="width: 190px; margin-left: 12px">
            <el-option v-for="item in knowledgeBases" :key="item.slug" :label="item.name" :value="item.slug" />
          </el-select>
        </div>

        <div class="messages-container" ref="msgContainer">
          <div v-if="store.messages.length === 0" class="empty-chat">
            <el-icon :size="48" color="#c0c4cc"><ChatDotRound /></el-icon>
            <p>开始您的法律咨询</p>
            <div class="example-prompts">
              <el-button
                v-for="q in examples"
                :key="q"
                size="small"
                @click="handleQuickAsk(q)"
                class="example-btn"
              >
                {{ q.slice(0, 25) }}…
              </el-button>
            </div>
            <div v-if="store.recommendations.length" class="recommendations"><p>为你推荐</p><el-button v-for="item in store.recommendations.filter(item => item.questions?.length)" :key="item.label" size="small" @click="handleQuickAsk(item.questions![0])">{{ item.questions![0] }}</el-button></div>
          </div>

          <div
            v-for="(msg, index) in store.messages"
            :key="msg.id"
            :class="['message', msg.role]"
          >
            <div class="msg-avatar"><el-icon><UserFilled v-if="msg.role === 'user'" /><ChatDotRound v-else /></el-icon></div>
            <div class="msg-body">
              <div class="msg-content markdown-body" v-html="renderMarkdown(msg.content)" />
              <div v-if="msg.role === 'assistant' && msg.cacheHit === 'semantic'" class="cache-hint">
                基于相似问题“{{ msg.cacheOriginalQuery }}”的缓存结果（相似度 {{ msg.cacheSimilarity }}）
              </div>
              <details v-if="msg.role === 'assistant' && msg.workflowTrace?.length" class="workflow-summary">
                <summary>
                  证据工作流
                  <span :class="['workflow-status', msg.workflowStatus || 'completed']">
                    {{ msg.workflowStatus === 'degraded' ? '部分降级' : '已完成' }}
                  </span>
                  <span v-if="msg.evidenceCount !== undefined">{{ msg.evidenceCount }} 条证据</span>
                </summary>
                <ul>
                  <li v-for="event in msg.workflowTrace" :key="`${event.node}-${event.duration_ms}`">
                    <strong>{{ workflowNodeLabel(event.node) }}</strong>
                    <span :class="['event-status', event.status]">{{ workflowEventLabel(event.status) }}</span>
                    <span>{{ event.duration_ms }} ms</span>
                    <span v-if="event.output_count">输出 {{ event.output_count }}</span>
                    <span v-if="event.reason">（{{ event.reason }}）</span>
                  </li>
                </ul>
              </details>
              <div v-if="msg.citations && msg.citations.length" class="msg-citations">
                <el-tag
                  v-for="c in msg.citations"
                  :key="c.article_id"
                  :type="c.is_verified ? 'success' : 'warning'"
                  size="small"
                  class="citation-tag"
                  @click="selectedCitation = c"
                >
                  {{ c.article_id }}
                </el-tag>
              </div>
              <el-button
                v-if="msg.role === 'assistant'"
                text
                size="small"
                :loading="favoriteLoading === msg.id"
                @click="toggleFavorite(msg, index)"
              >
                {{ favoriteIds[msg.id] ? '取消收藏' : '收藏回答' }}
              </el-button>
            </div>
          </div>

          <div v-if="store.isLoading" class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
        </div>

        <div class="input-area">
          <el-input
            v-model="inputText"
            placeholder="请输入您的法律问题…"
            :disabled="store.isLoading"
            @keyup.enter="handleSend"
            size="large"
          >
            <template #append>
              <el-button
                :loading="store.isLoading"
                @click="handleSend"
                type="primary"
              >
                发送
              </el-button>
            </template>
          </el-input>
        </div>
      </div>

      <!-- 右栏：法条溯源 -->
      <div class="citation-panel">
        <div class="panel-header"><el-icon><Reading /></el-icon><span>法条溯源</span></div>
        <div class="citation-content">
          <div v-if="visibleCitations.length" class="citation-list">
            <div
              v-for="(c, index) in visibleCitations"
              :key="`${c.article_id}-${c.citation_text}-${index}`"
              :class="['citation-card', { active: selectedCitation === c }]"
              @click="selectedCitation = c"
            >
              <div class="citation-card-header">
                <strong>{{ c.article_id }}</strong>
                <el-tag :type="c.is_verified ? 'success' : 'warning'" size="small">
                  {{ c.is_verified ? '已校验' : '待核实' }}
                </el-tag>
              </div>
              <div class="citation-card-text">
                {{ c.citation_text || '点击查看详情' }}
              </div>
            </div>
          </div>
          <div v-if="selectedCitation" class="citation-detail">
            <h4>{{ selectedCitation.article_id }}</h4>
            <el-tag :type="selectedCitation.is_verified ? 'success' : 'danger'" size="small">
              {{ selectedCitation.is_verified ? '✅ 已校验' : '❌ 待核实' }}
            </el-tag>
            <div class="citation-text">{{ selectedCitation.citation_text || '（暂无引用上下文）' }}</div>
            <el-divider />
            <h4>📜 原文</h4>
            <div class="citation-original" v-html="renderMarkdown(selectedCitation.original_text || '知识库中暂未收录该法条全文')" />
          </div>
          <div v-if="!visibleCitations.length" class="empty-trace">
            <el-icon :size="36" color="#c0c4cc"><Reading /></el-icon>
            <p>发送问题后，点击回答中的法条标签查看原文</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>


<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { knowledgeBaseApi, type KnowledgeBase } from '@/api/knowledgeBases'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import type { Citation } from '@/api/query'
import { favoritesApi } from '@/api/favorites'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'

const route = useRoute()
const router = useRouter()
const store = useChatStore()

const inputText = ref('')
const selectedCitation = ref<Citation | null>(null)
const msgContainer = ref<HTMLElement>()
const knowledgeBases = ref<KnowledgeBase[]>([])
const knowledgeBaseId = ref('')
const favoriteIds = ref<Record<string, number>>({})
const favoriteLoading = ref<string | null>(null)
const sessionQuery = ref('')

const md = new MarkdownIt({ breaks: true, linkify: true })

const examples = [
  '合同成立需要满足哪些条件？',
  '格式条款什么情况下无效？',
  '定金和订金有什么区别？',
]

const lastMessage = computed(() => {
  const msgs = store.messages
  return msgs.length ? msgs[msgs.length - 1] : null
})

const latestCitations = computed(() => {
  // 从最新一条助手消息中提取 citations
  for (let i = store.messages.length - 1; i >= 0; i--) {
    const msg = store.messages[i]
    if (msg.role === 'assistant' && msg.citations?.length) {
      return msg.citations
    }
  }
  return []
})

const visibleCitations = computed(() => {
  const seen = new Set<string>()
  return latestCitations.value.filter((citation) => {
    const key = `${citation.article_id}|${citation.citation_text}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})

function renderMarkdown(text: string): string {
  return md.render(text || '')
}

function workflowNodeLabel(node: string): string {
  return {
    planning: '问题拆解',
    routing: '检索路由',
    statute_retrieval: '法条检索',
    case_retrieval: '案例检索',
    graph_retrieval: '图谱检索',
    evidence_ledger: '证据汇总',
    answer: '回答生成',
    citation_verifier: '引用校验',
    repair: '受控修复',
  }[node] || node
}

function workflowEventLabel(status: string): string {
  return {
    completed: '完成',
    degraded: '降级',
    failed: '未通过',
    skipped: '跳过',
  }[status] || status
}

async function handleSend() {
  const q = inputText.value.trim()
  if (!q || store.isLoading) return
  inputText.value = ''
  await store.sendMessage(q, knowledgeBaseId.value)
  if (store.currentSessionId) await router.replace(`/chat/${store.currentSessionId}`)
  await nextTick()
  scrollToBottom()
}

async function newSession() {
  try {
    const session = await store.createSession()
    await router.push(`/chat/${session.id}`)
  } catch {
    ElMessage.error('创建会话失败，请稍后重试')
    return
  }
  selectedCitation.value = null
}

async function openSession(sessionId: string) {
  try {
    await store.loadSession(sessionId)
    await router.push(`/chat/${sessionId}`)
    await nextTick()
    scrollToBottom()
  } catch {
    ElMessage.error('会话不可用或已归档')
    await store.loadSessions(sessionQuery.value)
  }
}

async function searchSessions() {
  await store.loadSessions(sessionQuery.value)
}

async function handleSessionCommand(command: string, sessionId: string) {
  if (command === 'archive') {
    await store.archiveSession(sessionId)
    if (!store.currentSessionId) await router.push('/chat')
    return
  }
  const session = store.sessions.find(item => item.id === sessionId)
  const title = window.prompt('请输入新的会话标题', session?.title || '')
  if (title?.trim()) await store.renameSession(sessionId, title.trim())
}

function handleQuickAsk(q: string) {
  inputText.value = q
  handleSend()
}

async function toggleFavorite(msg: typeof store.messages[number], index: number) {
  if (favoriteLoading.value) return
  const existingId = favoriteIds.value[msg.id]
  favoriteLoading.value = msg.id
  try {
    if (existingId) {
      await favoritesApi.remove(existingId)
      delete favoriteIds.value[msg.id]
      ElMessage.success('已取消收藏')
      return
    }
    const question = [...store.messages.slice(0, index)].reverse().find((item) => item.role === 'user')?.content
    if (!question) {
      ElMessage.warning('未找到对应问题，暂不能收藏')
      return
    }
    const favorite = await favoritesApi.create({
      question,
      answer: msg.content,
      citations: msg.citations || [],
      knowledge_base_slug: msg.knowledgeBaseSlug || knowledgeBaseId.value || null,
      law_area: null,
    })
    favoriteIds.value[msg.id] = favorite.id
    ElMessage.success('已收藏')
  } catch {
    ElMessage.error('收藏操作失败')
  } finally {
    favoriteLoading.value = null
  }
}

function scrollToBottom() {
  if (msgContainer.value) {
    msgContainer.value.scrollTop = msgContainer.value.scrollHeight
  }
}

// 路由参数预填充
onMounted(async () => {
  const q = route.query.q as string
  if (q) {
    inputText.value = q
  }
  knowledgeBaseApi.list().then(items => {
    knowledgeBases.value = items.filter(item => item.status === 'READY')
    const requestedKnowledgeBase = route.query.kb as string | undefined
    knowledgeBaseId.value = knowledgeBases.value.find(item => item.slug === requestedKnowledgeBase)?.slug
      || knowledgeBases.value[0]?.slug
      || ''
  })
  await store.loadSessions()
  await store.loadRecommendations()
  const sessionId = route.params.sessionId as string | undefined
  if (sessionId) await openSession(sessionId)
})

watch(() => route.params.sessionId, async (sessionId) => {
  if (typeof sessionId === 'string' && sessionId !== store.currentSessionId) await openSession(sessionId)
})

// 自动滚动
watch(() => store.messages.length, () => {
  nextTick(scrollToBottom)
})
</script>

<style scoped>
.chat-page { height: calc(100vh - 48px); }

.chat-layout {
  display: flex;
  gap: 12px;
  height: 100%;
}

.session-panel { width: 248px; flex: 0 0 248px; background: var(--surface-raised); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 12px; display: flex; flex-direction: column; overflow: hidden; }
.session-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; color: var(--text-primary); }
.session-list { overflow-y: auto; margin-top: 10px; }
.session-item { display: flex; align-items: center; gap: 4px; padding: 9px 4px 9px 8px; border-radius: var(--radius-sm); cursor: pointer; color: var(--text-primary); }
.session-item:hover, .session-item.active { background: var(--surface-selected); color: var(--brand-primary); }
.session-title { flex: 1; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: 13px; }
.recommendations { margin-top: 20px; display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; }.recommendations p { width: 100%; margin: 0; font-size: 12px; color: #909399; }

/* 双栏宽度比：对话区 : 法条溯源 = 2 : 1 */
.chat-panel { flex: 2; display: flex; flex-direction: column; background: var(--surface-raised); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden; }
.citation-panel { flex: 1; background: var(--surface-raised); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden; display: flex; flex-direction: column; min-width: 280px; }

.panel-header {
  padding: 14px 16px;
  font-weight: 600;
  font-size: 15px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface-subtle);
  display: flex;
  align-items: center;
  gap: 8px;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.empty-chat {
  text-align: center;
  padding: 60px 20px;
  color: #c0c4cc;
}

.example-prompts { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 16px; }
.example-btn { max-width: 200px; }

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.message.user { flex-direction: row-reverse; }
.message.user .msg-body { background: var(--surface-selected); border-radius: var(--radius-md) var(--radius-sm) var(--radius-md) var(--radius-md); }
.message.assistant .msg-body { background: var(--surface-subtle); border-radius: var(--radius-sm) var(--radius-md) var(--radius-md) var(--radius-md); }

.msg-avatar { width: 32px; height: 32px; display: grid; place-items: center; color: var(--brand-primary); background: var(--surface-selected); border: 1px solid var(--brand-soft); border-radius: 50%; flex-shrink: 0; }

.msg-body { padding: 12px 16px; max-width: 80%; }
.cache-hint { margin-top: 8px; color: #909399; font-size: 12px; }
.workflow-summary { margin-top: 8px; color: #606266; font-size: 12px; }
.workflow-summary summary { cursor: pointer; color: var(--brand-primary); }
.workflow-summary summary span { margin-left: 6px; }
.workflow-summary ul { margin: 6px 0 0; padding-left: 16px; }
.workflow-summary li { margin: 4px 0; }
.workflow-summary li span { margin-left: 6px; color: #909399; }
.workflow-status, .event-status { border-radius: 4px; padding: 1px 4px; }
.workflow-status.completed, .event-status.completed { color: #167c3b; background: #e8f6ee; }
.workflow-status.degraded, .event-status.degraded, .event-status.skipped { color: #9a6700; background: #fff8c5; }
.event-status.failed { color: #b42318; background: #fee4e2; }

.msg-citations { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
.citation-tag { cursor: pointer; }

.typing-indicator {
  display: flex; gap: 6px; padding: 12px 16px;
}
.typing-indicator span {
  width: 8px; height: 8px; border-radius: 50%; background: #c0c4cc; animation: bounce 1.4s infinite both;
}
.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.input-area { padding: 12px 16px; border-top: 1px solid var(--border-subtle); background: var(--surface-raised); }

.trace-content, .citation-content {
  flex: 1; overflow-y: auto; padding: 12px;
}

.citation-list { display: flex; flex-direction: column; gap: 8px; max-height: 250px; overflow-y: auto; }

.citation-card {
  padding: 10px 12px; background: var(--surface-subtle); border-radius: var(--radius-sm); cursor: pointer;
  border: 1px solid transparent; transition: all 0.2s;
}
.citation-card:hover { border-color: var(--brand-primary); background: var(--surface-selected); }
.citation-card.active { border-color: var(--brand-primary); background: var(--surface-selected); }
.citation-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.citation-card-header strong { font-size: 13px; color: var(--text-primary); }
.citation-card-text { font-size: 12px; color: #909399; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.empty-trace {
  text-align: center; padding: 40px 16px; color: #c0c4cc;
}

.citation-detail { padding: 16px 0 8px; }
.citation-detail h4 { font-size: 14px; color: var(--text-primary); margin: 0 0 8px; }
.citation-text { font-size: 14px; color: var(--text-secondary); margin: 12px 0; padding: 12px; background: var(--surface-subtle); border-radius: var(--radius-sm); }
.citation-original { font-size: 13px; color: var(--text-primary); }

@media (max-width: 1180px) { .session-panel { width: 208px; flex-basis: 208px; } .citation-panel { min-width: 240px; } }
@media (max-width: 900px) { .chat-page { height: auto; } .chat-layout { min-height: calc(100vh - 32px); } .session-panel { display: none; } .citation-panel { display: none; } }
</style>
