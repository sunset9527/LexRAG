<template>
  <div class="provider-selector">
    <button
      v-for="provider in providers"
      :key="provider.key"
      type="button"
      :data-provider="provider.key"
      :class="['provider-card', { active: modelValue === provider.key }]"
      @click="emit('update:modelValue', provider.key)"
    >
      <span class="provider-name">{{ provider.label }}</span>
      <span class="provider-models">{{ provider.models.length }} 个模型</span>
    </button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: string
  providers: Array<{ key: string; label: string; models: string[] }>
}>()

const emit = defineEmits<{ 'update:modelValue': [key: string] }>()
</script>

<style scoped>
.provider-selector { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.provider-card {
  padding: 16px; border: 2px solid #ebeef5; border-radius: 10px;
  cursor: pointer; transition: all 0.15s; text-align: center; background: #fff;
}
.provider-card:hover, .provider-card.active { border-color: #2d5cc5; background: #e8f0fe; }
.provider-name { display: block; font-weight: 600; color: #303133; margin-bottom: 4px; }
.provider-models { font-size: 12px; color: #909399; }
</style>
