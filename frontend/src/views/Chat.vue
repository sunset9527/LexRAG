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
          <el-select v-model="knowledgeBaseId" multiple clearable collapse-tags size="small" aria-label="选择检索知识库，留空自动选择" placeholder="自动选择知识库" style="width: 240px; margin-left: 12px">
            <el-option v-for="item in knowledgeBases" :key="item.slug" :label="item.name" :value="item.slug" />
          </el-select>
          <el-date-picker v-model="caseDate" value-format="YYYY-MM-DD" type="date" size="small" clearable placeholder="案件发生日期（可选）" style="width: 190px" />
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
              <div v-if="msg.role === 'assistant' && msg.knowledgeBaseRouting" class="cache-hint">
                {{ msg.knowledgeBaseRouting.mode === 'automatic' ? '系统自动选择法规库：' : '指定法规库：' }}
                {{ msg.knowledgeBaseRouting.selected_slugs.join('、') }}
              </div>
              <div v-if="msg.role === 'assistant' && msg.routingCandidates?.length" class="routing-candidates">
                <span>请选择法规库后重问：</span>
                <el-button
                  v-for="candidate in msg.routingCandidates"
                  :key="candidate.slug"
                  size="small"
                  :disabled="store.isLoading"
                  @click="retryWithKnowledgeBase(index, candidate.slug)"
                >
                  {{ knowledgeBaseLabel(candidate.slug) }}
                </el-button>
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
          <div v-if="store.isLoading" class="stream-progress">
            <span>{{ store.streamStatus === 'reconnecting' ? '正在重新连接事件流…' : '正在处理法律咨询…' }}</span>
            <span>已用 {{ activeElapsed }}</span>
            <el-tag v-for="stage in store.activeStages" :key="`${stage.stage}-${stage.duration_ms}`" size="small">
              {{ workflowNodeLabel(stage.stage) }} · {{ workflowEventLabel(stage.status) }}
            </el-tag>
            <el-button text type="danger" size="small" @click="store.cancelActiveQuery">取消</el-button>
          </div>
        </div>

        <ChatComposer v-model="inputText" :disabled="store.isLoading" @submit="handleSend" />
      </div>

      <!-- 右栏：法条溯源 -->
      <div class="citation-panel">
        <div class="panel-header"><el-icon><Reading /></el-icon><span>法条溯源</span></div>
        <div class="citation-content">
          <section v-if="latestVersionSelection" class="version-card">
            <h4>适用版本</h4>
            <p><strong>{{ latestVersionSelection.version_id }}</strong></p>
            <p>适用日期：{{ latestVersionSelection.effective_from }}{{ latestVersionSelection.effective_to ? ` 至 ${latestVersionSelection.effective_to}` : ' 起' }}</p>
            <el-alert v-if="latestVersionSelection.assumption" type="warning" :title="latestVersionSelection.assumption" :closable="false" />
            <el-link :href="latestVersionSelection.source_url" target="_blank" type="primary">查看官方来源</el-link>
            <details v-if="latestVersionSelection.timeline.length" class="version-timeline"><summary>版本时间线</summary><ul><li v-for="item in latestVersionSelection.timeline" :key="item.target_version_id">{{ item.target_version_id }}：{{ item.effective_from }}{{ item.effective_to ? ` 至 ${item.effective_to}` : ' 起' }}</li></ul></details>
          </section>
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
            <p v-if="selectedCitation.knowledge_base_slug">知识库：{{ selectedCitation.knowledge_base_slug }}</p>
            <p v-if="selectedCitation.source_type">来源类型：{{ selectedCitation.source_type }}</p>
            <p v-if="selectedCitation.retrieval_paths?.length">检索路径：{{ selectedCitation.retrieval_paths.join('、') }}</p>
            <p v-if="selectedCitation.version_id">版本：{{ selectedCitation.version_id }}</p>
            <p v-if="selectedCitation.effective_from">生效：{{ selectedCitation.effective_from }}{{ selectedCitation.effective_to ? ` 至 ${selectedCitation.effective_to}` : ' 起' }}</p>
            <el-link v-if="selectedCitation.source_url" :href="selectedCitation.source_url" target="_blank" type="primary">查看法规来源</el-link>
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
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { knowledgeBaseApi, type KnowledgeBase } from '@/api/knowledgeBases'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import type { Citation } from '@/api/query'
import type { VersionSelection } from '@/api/query'
import { favoritesApi } from '@/api/favorites'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import { formatElapsedSeconds } from '@/utils/queryRunProgress'
import ChatComposer from '@/components/chat/ChatComposer.vue'

const route = useRoute()
const router = useRouter()
const store = useChatStore()

const inputText = ref('')
const selectedCitation = ref<Citation | null>(null)
const msgContainer = ref<HTMLElement>()
const knowledgeBases = ref<KnowledgeBase[]>([])
const knowledgeBaseId = ref<string[]>([])
const favoriteIds = ref<Record<string, number>>({})
const favoriteLoading = ref<string | null>(null)
const sessionQuery = ref('')
const caseDate = ref('')
const streamClock = ref(Date.now())
let streamClockTimer: ReturnType<typeof setInterval> | undefined

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

const activeElapsed = computed(() => {
  const startedAt = store.activeRunStartedAt
  return startedAt ? formatElapsedSeconds(startedAt, streamClock.value) : '0 秒'
})

watch(() => store.isLoading, (isLoading) => {
  if (streamClockTimer) clearInterval(streamClockTimer)
  if (isLoading) {
    streamClock.value = Date.now()
    streamClockTimer = setInterval(() => { streamClock.value = Date.now() }, 1_000)
  }
})

onUnmounted(() => {
  if (streamClockTimer) clearInterval(streamClockTimer)
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

const latestVersionSelection = computed<VersionSelection | undefined>(() => {
  for (let i = store.messages.length - 1; i >= 0; i--) {
    const message = store.messages[i]
    if (message.role === 'assistant' && message.versionSelection) return message.versionSelection
  }
  return undefined
})

function renderMarkdown(text: string): string {
  return md.render(text || '')
}

function workflowNodeLabel(node: string): string {
  return {
    planning: '问题拆解',
    knowledge_base_routing: '知识库路由',
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

function knowledgeBaseLabel(slug: string): string {
  return knowledgeBases.value.find((item) => item.slug === slug)?.name || slug
}

async function retryWithKnowledgeBase(messageIndex: number, slug: string) {
  if (store.isLoading) return
  const question = [...store.messages.slice(0, messageIndex)].reverse().find((item) => item.role === 'user')?.content
  if (!question) {
    ElMessage.warning('未找到需要重问的问题')
    return
  }
  knowledgeBaseId.value = [slug]
  await store.sendMessage(question, [slug], caseDate.value || undefined)
  if (store.currentSessionId) await router.replace(`/chat/${store.currentSessionId}`)
  await nextTick()
  scrollToBottom()
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
  await store.sendMessage(q, knowledgeBaseId.value, caseDate.value || undefined)
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
      knowledge_base_slug: msg.knowledgeBaseSlug || knowledgeBaseId.value.join('|') || null,
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
    knowledgeBaseId.value = requestedKnowledgeBase && knowledgeBases.value.some(item => item.slug === requestedKnowledgeBase)
      ? [requestedKnowledgeBase]
      : []
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
.routing-candidates { margin-top: 8px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; font-size: 12px; color: #606266; }
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
.stream-progress { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 0 16px 12px; color: var(--text-secondary); font-size: 12px; }
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
.version-card { margin-bottom: 12px; padding: 12px; border: 1px solid var(--brand-soft); border-radius: var(--radius-sm); background: var(--surface-selected); }
.version-card h4, .version-card p { margin: 0 0 8px; font-size: 13px; color: var(--text-primary); word-break: break-word; }
.version-timeline { margin-top: 10px; font-size: 12px; color: var(--text-secondary); }.version-timeline summary { cursor: pointer; }.version-timeline ul { padding-left: 16px; margin: 6px 0 0; }.version-timeline li { margin: 4px 0; }
.citation-detail h4 { font-size: 14px; color: var(--text-primary); margin: 0 0 8px; }
.citation-text { font-size: 14px; color: var(--text-secondary); margin: 12px 0; padding: 12px; background: var(--surface-subtle); border-radius: var(--radius-sm); }
.citation-original { font-size: 13px; color: var(--text-primary); }

@media (max-width: 1180px) { .session-panel { width: 208px; flex-basis: 208px; } .citation-panel { min-width: 240px; } }
@media (max-width: 900px) { .chat-page { height: auto; } .chat-layout { min-height: calc(100vh - 32px); } .session-panel { display: none; } .citation-panel { display: none; } }
</style>
