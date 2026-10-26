<template>
  <div class="input-area">
    <el-input
      :model-value="modelValue"
      placeholder="请输入您的法律问题…"
      :disabled="disabled"
      size="large"
      @update:model-value="emit('update:modelValue', $event)"
      @keyup.enter="emit('submit')"
    >
      <template #append>
        <el-button :loading="disabled" type="primary" @click="emit('submit')">发送</el-button>
      </template>
    </el-input>
  </div>
</template>

<script setup lang="ts">
defineProps<{ modelValue: string; disabled: boolean }>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  submit: []
}>()
</script>
