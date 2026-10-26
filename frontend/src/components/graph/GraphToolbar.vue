<template>
  <div class="graph-actions">
    <el-select
      :model-value="modelValue"
      placeholder="选择法律"
      size="default"
      style="width: 180px"
      @update:model-value="emit('update:modelValue', $event)"
    >
      <el-option label="全部法规" value="" />
      <el-option v-for="law in laws" :key="law" :label="law" :value="law" />
    </el-select>
    <el-button type="primary" @click="emit('load')">加载图谱</el-button>
    <el-button @click="emit('reset')">重置</el-button>
  </div>
</template>

<script setup lang="ts">
defineProps<{ modelValue: string; laws: string[] }>()

const emit = defineEmits<{
  'update:modelValue': [law: string]
  load: []
  reset: []
}>()
</script>
