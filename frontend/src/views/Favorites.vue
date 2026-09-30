<template>
  <div class="favorites-page">
    <div class="page-header">
      <h2>⭐ 我的收藏</h2>
      <el-button :loading="loading" @click="loadFavorites">刷新</el-button>
    </div>
    <el-empty v-if="!loading && favorites.length === 0" description="还没有收藏的法律问答" />
    <el-card v-for="favorite in favorites" :key="favorite.id" class="favorite-card" shadow="never">
      <template #header>
        <div class="card-header">
          <strong>{{ favorite.question }}</strong>
          <el-button type="danger" text @click="removeFavorite(favorite.id)">取消收藏</el-button>
        </div>
      </template>
      <p class="answer">{{ favorite.answer }}</p>
      <div class="meta">
        <el-tag size="small">{{ favorite.knowledge_base_slug || '未标注知识库' }}</el-tag>
        <el-tag v-if="favorite.law_area" size="small" type="info">{{ favorite.law_area }}</el-tag>
        <span>{{ favorite.citations.length }} 条引用</span>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { favoritesApi, type Favorite } from '@/api/favorites'

const favorites = ref<Favorite[]>([])
const loading = ref(false)

async function loadFavorites() {
  loading.value = true
  try {
    favorites.value = await favoritesApi.list()
  } catch {
    ElMessage.error('收藏列表加载失败')
  } finally {
    loading.value = false
  }
}

async function removeFavorite(id: number) {
  try {
    await favoritesApi.remove(id)
    favorites.value = favorites.value.filter((item) => item.id !== id)
    ElMessage.success('已取消收藏')
  } catch {
    ElMessage.error('取消收藏失败')
  }
}

onMounted(loadFavorites)
</script>

<style scoped>
.favorites-page { max-width: 960px; margin: 0 auto; }
.page-header, .card-header { display: flex; align-items: center; justify-content: space-between; }
.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 20px; color: #0f1f3d; }
.favorite-card { margin-bottom: 12px; border-radius: 12px; }
.answer { white-space: pre-wrap; color: #303133; line-height: 1.7; }
.meta { display: flex; gap: 8px; align-items: center; color: #909399; font-size: 12px; }
</style>
