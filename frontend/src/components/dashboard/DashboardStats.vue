<template>
  <el-row :gutter="20" class="stats-row">
    <el-col v-for="item in items" :key="item.label" :span="6">
      <div class="stat-card">
        <div class="stat-value">{{ item.value }}<span v-if="item.suffix">{{ item.suffix }}</span></div>
        <div class="stat-label">{{ item.label }}</div>
      </div>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  stats: {
    lawCount: string
    caseCount: string
    verifyRate: string
    queryCount: string
  }
}>()

const items = computed(() => [
  { label: '收录法条', value: props.stats.lawCount },
  { label: '参考案例', value: props.stats.caseCount },
  { label: '法条校验率', value: props.stats.verifyRate, suffix: '%' },
  { label: '今日咨询', value: props.stats.queryCount },
])
</script>

<style scoped>
.stats-row { margin-bottom: 20px; }
.stat-card {
  background: #fff;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 18px;
  box-shadow: none;
  transition: box-shadow 0.2s;
}
.stat-card:hover { border-color: var(--border-strong); box-shadow: var(--shadow-panel); }
.stat-value { font-size: 22px; font-weight: 700; color: var(--text-primary); font-variant-numeric: tabular-nums; }
.stat-label { font-size: 13px; color: var(--text-secondary); margin-top: 2px; }
</style>
