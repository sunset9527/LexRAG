<template>
  <div class="chat-page">
    <!-- 双栏布局 -->
    <div class="chat-layout">
      <!-- 左栏：对话区 -->
      <div class="chat-panel">
        <div class="panel-header">💬 法律咨询
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
          </div>

          <div
            v-for="msg in store.messages"
            :key="msg.id"
            :class="['message', msg.role]"
          >
            <div class="msg-avatar">
              {{ msg.role === 'user' ? '😀' : '⚖️' }}
            </div>
            <div class="msg-body">
              <div class="msg-content markdown-body" v-html="renderMarkdown(msg.content)" />
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
        <div class="panel-header">📖 法条溯源</div>
        <div class="citation-content">
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
          <div v-else-if="latestCitations.length" class="citation-list">
            <div
              v-for="c in latestCitations"
              :key="c.article_id"
              class="citation-card"
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
          <div v-else class="empty-trace">
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
import { useRoute } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import type { Citation } from '@/api/query'
import MarkdownIt from 'markdown-it'

const route = useRoute()
const store = useChatStore()

const inputText = ref('')
const selectedCitation = ref<Citation | null>(null)
const msgContainer = ref<HTMLElement>()
const knowledgeBases = ref<KnowledgeBase[]>([])
const knowledgeBaseId = ref('')

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

function renderMarkdown(text: string): string {
  return md.render(text || '')
}

async function handleSend() {
  const q = inputText.value.trim()
  if (!q || store.isLoading) return
  inputText.value = ''
  await store.sendMessage(q, knowledgeBaseId.value)
  await nextTick()
  scrollToBottom()
}

function handleQuickAsk(q: string) {
  inputText.value = q
  handleSend()
}

function scrollToBottom() {
  if (msgContainer.value) {
    msgContainer.value.scrollTop = msgContainer.value.scrollHeight
  }
}

// 路由参数预填充
onMounted(() => {
  const q = route.query.q as string
  if (q) {
    inputText.value = q
  }
  knowledgeBaseApi.list().then(items => {
    knowledgeBases.value = items.filter(item => item.status === 'READY')
    knowledgeBaseId.value = knowledgeBases.value[0]?.slug || ''
  })
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
  gap: 16px;
  height: 100%;
}

/* 双栏宽度比：对话区 : 法条溯源 = 2 : 1 */
.chat-panel { flex: 2; display: flex; flex-direction: column; background: #fff; border-radius: 12px; overflow: hidden; }
.citation-panel { flex: 1; background: #fff; border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; min-width: 280px; }

.panel-header {
  padding: 14px 16px;
  font-weight: 600;
  font-size: 15px;
  border-bottom: 1px solid #ebeef5;
  background: #fafbfc;
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
.message.user .msg-body { background: #e8f0fe; border-radius: 12px 4px 12px 12px; }
.message.assistant .msg-body { background: #f5f7fa; border-radius: 4px 12px 12px 12px; }

.msg-avatar { font-size: 28px; flex-shrink: 0; line-height: 1; }

.msg-body { padding: 12px 16px; max-width: 80%; }

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

.input-area { padding: 12px 16px; border-top: 1px solid #ebeef5; }

.trace-content, .citation-content {
  flex: 1; overflow-y: auto; padding: 12px;
}

.citation-list { display: flex; flex-direction: column; gap: 8px; }

.citation-card {
  padding: 10px 12px; background: #f8f9fb; border-radius: 8px; cursor: pointer;
  border: 1px solid transparent; transition: all 0.2s;
}
.citation-card:hover { border-color: #2d5cc5; background: #eef2fb; }
.citation-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.citation-card-header strong { font-size: 13px; color: #0f1f3d; }
.citation-card-text { font-size: 12px; color: #909399; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.empty-trace {
  text-align: center; padding: 40px 16px; color: #c0c4cc;
}

.citation-detail { padding: 8px 0; }
.citation-detail h4 { font-size: 14px; color: #0f1f3d; margin: 0 0 8px; }
.citation-text { font-size: 14px; color: #606266; margin: 12px 0; padding: 12px; background: #f8f9fb; border-radius: 8px; }
.citation-original { font-size: 13px; color: #303133; }
</style>
