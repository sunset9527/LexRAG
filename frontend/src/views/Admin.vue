<template>
  <section class="admin-page">
    <h1>企业管理后台</h1>
    <el-alert title="管理操作受后端组织权限控制；本页仅展示当前组织允许的数据。" type="info" :closable="false" />
    <el-card v-loading="loading" class="card"><template #header>当前组织</template><p>{{ organization?.name || '未加载' }}</p><el-tag>{{ organization?.role || '-' }}</el-tag></el-card>
    <el-card v-if="organization?.role === 'admin'" class="card"><template #header>成员与角色</template>
      <el-table :data="members"><el-table-column prop="username" label="成员"/><el-table-column prop="role" label="角色"/><el-table-column label="调整"><template #default="scope"><el-select v-model="scope.row.role" size="small" @change="changeRole(scope.row)"><el-option value="admin" label="管理员"/><el-option value="lawyer" label="律师"/><el-option value="member" label="普通用户"/></el-select></template></el-table-column></el-table>
    </el-card>
    <el-card v-if="organization?.role === 'admin'" class="card"><template #header>法规更新订阅</template>
      <el-form inline @submit.prevent="createSubscription"><el-form-item label="法规名称"><el-input v-model="lawName" /></el-form-item><el-form-item label="权威来源 URL"><el-input v-model="sourceUrl" /></el-form-item><el-button type="primary" native-type="submit">新增订阅</el-button></el-form>
      <el-table :data="subscriptions"><el-table-column prop="law_name" label="法规"/><el-table-column prop="source_url" label="来源"/><el-table-column prop="last_content_hash" label="最近快照哈希"/></el-table>
      <el-alert class="hint" title="生产环境应由已授权的采集任务提交来源快照；系统发现变化后必须在后台确认，不能自动入库。" type="warning" :closable="false" />
    </el-card>
    <el-card v-if="organization?.role === 'admin'" class="card"><template #header>用量与审计</template>
      <el-descriptions :column="3" border><el-descriptions-item label="近 90 天查询">{{ totalQueries }}</el-descriptions-item><el-descriptions-item label="脱敏审计事件">{{ auditLogs.length }}</el-descriptions-item><el-descriptions-item label="原始问答">不保存</el-descriptions-item></el-descriptions>
      <el-table :data="auditLogs" max-height="260"><el-table-column prop="created_at" label="时间"/><el-table-column prop="action" label="动作"/><el-table-column prop="status" label="结果"/><el-table-column prop="target_type" label="对象"/></el-table>
    </el-card>
    <el-card v-if="organization?.role === 'admin'" class="card"><template #header>Agent 安全配置</template>
      <el-form inline @submit.prevent="saveAgentConfig"><el-form-item label="Top-K"><el-input-number v-model="agentConfig.top_k" :min="1" :max="20" /></el-form-item><el-form-item label="超时（秒）"><el-input-number v-model="agentConfig.timeout_seconds" :min="5" :max="120" /></el-form-item><el-form-item><el-checkbox v-model="agentConfig.case_search_enabled">案例检索</el-checkbox><el-checkbox v-model="agentConfig.graph_search_enabled">图谱检索</el-checkbox></el-form-item><el-button type="primary" native-type="submit">保存</el-button></el-form>
      <el-alert title="仅允许修改已列出的受控参数；不能从管理页执行 Python、Shell 或自定义工具代码。" type="info" :closable="false" />
    </el-card>
    <el-card v-if="organization?.role === 'admin'" class="card"><template #header>知识库与 Prompt 版本</template>
      <el-table :data="knowledgeBases" max-height="260"><el-table-column prop="name" label="知识库"/><el-table-column prop="status" label="状态"/><el-table-column prop="type" label="类型"/><el-table-column prop="chunk_count" label="Chunks"/></el-table>
      <el-table :data="prompts" max-height="260"><el-table-column prop="name" label="Prompt"/><el-table-column prop="version" label="版本"/><el-table-column prop="category" label="分类"/><el-table-column prop="updated_at" label="更新时间"/></el-table>
    </el-card>
    <el-card class="card"><template #header>v3.0 模块入口</template><el-space wrap><el-button @click="$router.push('/knowledge-bases')">知识库</el-button><el-button @click="$router.push('/settings')">Prompt</el-button><el-button @click="$router.push('/scenarios')">Agent 场景</el-button></el-space></el-card>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import client from '@/api/client'
const loading=ref(false); const organization=ref<{id:number,name:string,role:string}|null>(null); const members=ref<Array<{user_id:number,username:string,role:string}>>([])
const subscriptions=ref<Array<{id:number,law_name:string,source_url:string,last_content_hash:string|null}>>([]); const usage=ref<Array<{query_count:number}>>([]); const auditLogs=ref<Array<{created_at:string,action:string,status:string,target_type:string}>>([]); const knowledgeBases=ref<Array<{name:string,status:string,type:string,chunk_count:number}>>([]); const prompts=ref<Array<{name:string,version:number,category:string,updated_at:string}>>([])
const lawName=ref(''); const sourceUrl=ref(''); const totalQueries=computed(()=>usage.value.reduce((sum,item)=>sum+item.query_count,0))
const agentConfig=ref({case_search_enabled:true,graph_search_enabled:true,top_k:5,timeout_seconds:30})
async function load(){ loading.value=true; try { organization.value=(await client.get('/admin/organization')).data; if(organization.value?.role==='admin') { const [memberResponse,subscriptionResponse,usageResponse,auditResponse,agentConfigResponse,kbResponse,promptResponse]=await Promise.all([client.get('/admin/members'),client.get('/law-updates/subscriptions'),client.get('/admin/usage'),client.get('/admin/audit-logs'),client.get('/admin/agent-config'),client.get('/knowledge-bases'),client.get('/prompts')]); members.value=memberResponse.data.items; subscriptions.value=subscriptionResponse.data.items; usage.value=usageResponse.data.items; auditLogs.value=auditResponse.data.items; agentConfig.value={...agentConfig.value,...agentConfigResponse.data}; knowledgeBases.value=kbResponse.data.items; prompts.value=promptResponse.data.prompts } } finally { loading.value=false } }
async function changeRole(row:{user_id:number,role:string}){ await client.put(`/admin/members/${row.user_id}/role`,{role_code:row.role}); await load() }
async function createSubscription(){ if(!lawName.value||!sourceUrl.value)return; await client.post('/law-updates/subscriptions',{law_name:lawName.value,source_url:sourceUrl.value}); lawName.value=''; sourceUrl.value=''; await load() }
async function saveAgentConfig(){ await client.put('/admin/agent-config',agentConfig.value); await load() }
onMounted(load)
</script>
<style scoped>.admin-page{max-width:1100px;margin:auto}.card{margin-top:16px}.hint{margin-top:12px}</style>
