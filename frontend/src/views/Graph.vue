<template>
  <div class="graph-page">
    <div class="graph-header">
      <div>
        <h2><el-icon><Connection /></el-icon>法条引用知识图谱</h2>
        <p class="graph-desc">可视化法条间的引用关系，点击节点查看详情，拖动探索法律知识网络</p>
      </div>
      <GraphToolbar
        v-model="lawFilter"
        :laws="graphLaws"
        @load="loadGraph"
        @reset="resetGraph"
      />
    </div>

    <div class="graph-container">
      <div v-if="loading" class="graph-loading">
        <el-icon :size="40" class="is-loading"><Loading /></el-icon>
        <p>加载知识图谱…</p>
      </div>
      <div
        v-show="!loading"
        ref="chartRef"
        class="chart-area"
      />
    </div>

    <!-- 节点详情 -->
    <el-drawer v-model="drawerVisible" title="法条详情" size="400px">
      <div v-if="selectedNode" class="node-detail">
        <h3>{{ selectedNode.name }}</h3>
        <el-divider />
        <div class="detail-row">
          <span class="detail-label">法条编号</span>
          <span>{{ selectedNode.id }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">所属法律</span>
          <span>{{ selectedNode.law_name || '未标注' }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">引用次数</span>
          <el-tag size="small" type="primary">{{ selectedNode.symbolSize }} 次</el-tag>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { init, use, type ECharts } from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { queryApi } from '@/api/query'
import GraphToolbar from '@/components/graph/GraphToolbar.vue'

use([GraphChart, TooltipComponent, CanvasRenderer])

const chartRef = ref<HTMLElement>()
const graphContainer = ref<HTMLElement>()
const loading = ref(false)
const drawerVisible = ref(false)
const selectedNode = ref<any>(null)
const lawFilter = ref('')
const graphLaws = ref<string[]>([])

let chartInstance: ECharts | null = null

function buildGraphOption(graphData: any) {
  const nodes = graphData.nodes || []
  const links = graphData.links || []

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        if (params.dataType === 'node') {
          return `<strong>${params.name}</strong>`
        }
        return `${params.data.source} → ${params.data.target}`
      },
    },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      force: {
        repulsion: 500,
        edgeLength: [150, 300],
        gravity: 0.1,
      },
      data: nodes,
      links: links,
      label: {
        show: true,
        fontSize: 11,
        color: '#303133',
        formatter: (p: any) => p.name,
      },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 8,
      itemStyle: {
        color: '#2d5cc5',
        borderColor: '#1a3a7f',
        borderWidth: 1,
      },
      lineStyle: {
        color: '#c0c4cc',
        curveness: 0.2,
        opacity: 0.6,
      },
      emphasis: {
        focus: 'adjacency',
        itemStyle: { borderWidth: 2 },
        lineStyle: { width: 2 },
      },
    }],
  }
}

async function loadGraph() {
  loading.value = true
  try {
    const data = await queryApi.getGraph(lawFilter.value || undefined)
    graphLaws.value = data.available_laws || []
    const viz = data.visualization_data
    renderChart(viz || { nodes: [], links: [] })
  } catch {
    // 加载失败用空数据
    renderChart({ nodes: [], links: [] })
  } finally {
    loading.value = false
  }
}

function renderChart(data: any) {
  if (!chartRef.value) return

  // 确保容器有明确的像素尺寸
  const container = chartRef.value.parentElement
  if (container) {
    const rect = container.getBoundingClientRect()
    chartRef.value.style.width = rect.width + 'px'
    chartRef.value.style.height = rect.height + 'px'
  }

  if (!chartInstance) {
    chartInstance = init(chartRef.value)
    chartInstance.on('click', (params: any) => {
      if (params.dataType === 'node') {
        selectedNode.value = params.data
        drawerVisible.value = true
      }
    })
  }

  chartInstance.setOption(buildGraphOption(data), true)
  // ECharts 初始化后强制 resize，确保填满容器
  chartInstance.resize()
}

function resetGraph() {
  if (chartInstance) {
    chartInstance.dispatchAction({ type: 'restore' })
  }
}

function handleResize() {
  chartInstance?.resize()
}

onMounted(() => {
  loadGraph()
  window.addEventListener('resize', handleResize)
})

watch(lawFilter, loadGraph)

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
})
</script>

<style scoped>
.graph-page { height: calc(100vh - 48px); display: flex; flex-direction: column; }

.graph-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 16px;
}
.graph-header h2 { margin: 0 0 6px; font-size: 18px; color: #0f1f3d; }
.graph-desc { color: #909399; font-size: 13px; margin: 0; }
.graph-actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }

.graph-container {
  flex: 1; background: #fff; border-radius: 12px; overflow: hidden;
  position: relative; min-height: 0;
}

.graph-loading {
  position: absolute; inset: 0; z-index: 2;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: #c0c4cc; background: #fff;
}

.chart-area {
  position: absolute; inset: 0;
}

.node-detail h3 { margin: 0 0 12px; color: #0f1f3d; }
.detail-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 0; border-bottom: 1px solid #f5f5f5;
}
.detail-label { color: #909399; font-size: 13px; }
</style>
