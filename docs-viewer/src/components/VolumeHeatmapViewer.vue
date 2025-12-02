<script setup>
import { ref, computed, onMounted } from 'vue'

const props = defineProps({
  chartData: {
    type: Object,
    required: true
  }
})

const sortBy = ref('appearance') // 'appearance', 'avgVolume', 'maxVolume', 'name'
const sortDirection = ref('desc')
const searchQuery = ref('')
const showTopN = ref(30)
const colorScheme = ref('volume') // 'volume' or 'change'
const selectedPlatforms = ref([])
const minVolume = ref(0.1) // 默认100K = 0.1M

// 时间标签
const timeLabels = computed(() => {
  if (!props.chartData || !props.chartData.dates) return []
  return props.chartData.dates.map(date => {
    const d = new Date(date)
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })
})

// 所有平台列表
const allPlatforms = computed(() => {
  if (!props.chartData || !props.chartData.tokens) return []
  const platformsSet = new Set()
  Object.values(props.chartData.tokens).forEach(tokenData => {
    const platforms = tokenData.platforms || []
    platforms.forEach(p => platformsSet.add(p))
  })
  return Array.from(platformsSet).sort()
})

// 计算Token统计数据
const tokenStats = computed(() => {
  if (!props.chartData || !props.chartData.tokens) return []
  
  const stats = []
  for (const [token, data] of Object.entries(props.chartData.tokens)) {
    const volumes = data.volumes || data
    const platforms = data.platforms || []
    
    // 平台过滤
    if (selectedPlatforms.value.length > 0) {
      if (!platforms.some(p => selectedPlatforms.value.includes(p))) {
        continue
      }
    }
    
    const validVolumes = volumes.filter(v => v !== null && v > 0)
    const appearance = validVolumes.length
    const avgVolume = appearance > 0 ? validVolumes.reduce((a, b) => a + b, 0) / appearance : 0
    const maxVolume = appearance > 0 ? Math.max(...validVolumes) : 0
    const minVol = appearance > 0 ? Math.min(...validVolumes) : 0
    
    // 最小交易量过滤
    if (maxVolume < minVolume.value) {
      continue
    }
    
    stats.push({
      token,
      volumes,
      platforms,
      appearance,
      avgVolume,
      maxVolume,
      minVolume: minVol,
      appearanceRate: (appearance / props.chartData.dates.length * 100).toFixed(1)
    })
  }
  
  return stats
})

// 过滤和排序后的Token
const filteredAndSortedTokens = computed(() => {
  let filtered = tokenStats.value
  
  // 搜索过滤
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(stat => stat.token.toLowerCase().includes(query))
  }
  
  // 排序
  filtered.sort((a, b) => {
    let aVal, bVal
    switch (sortBy.value) {
      case 'appearance':
        aVal = a.appearance
        bVal = b.appearance
        break
      case 'avgVolume':
        aVal = a.avgVolume
        bVal = b.avgVolume
        break
      case 'maxVolume':
        aVal = a.maxVolume
        bVal = b.maxVolume
        break
      case 'name':
        aVal = a.token
        bVal = b.token
        return sortDirection.value === 'asc' 
          ? aVal.localeCompare(bVal) 
          : bVal.localeCompare(aVal)
      default:
        aVal = a.appearance
        bVal = b.appearance
    }
    
    return sortDirection.value === 'asc' ? aVal - bVal : bVal - aVal
  })
  
  // 限制显示数量
  return filtered.slice(0, showTopN.value)
})

// 获取单元格颜色
const getCellColor = (volume, maxVolume) => {
  if (volume === null || volume === 0) {
    return '#f5f5f5'
  }
  
  const ratio = volume / maxVolume
  
  if (colorScheme.value === 'volume') {
    // 蓝色渐变
    const intensity = Math.floor(ratio * 255)
    return `rgb(${255 - intensity}, ${255 - intensity * 0.5}, 255)`
  } else {
    // 绿色渐变
    const intensity = Math.floor(ratio * 200)
    return `rgb(${255 - intensity}, ${200 + intensity * 0.27}, ${150})`
  }
}

// 获取文本颜色
const getTextColor = (volume, maxVolume) => {
  if (volume === null || volume === 0) {
    return '#999'
  }
  
  const ratio = volume / maxVolume
  return ratio > 0.5 ? '#fff' : '#333'
}

// 格式化交易量
const formatVolume = (volume) => {
  if (volume === null || volume === 0) return '-'
  if (volume < 1) return volume.toFixed(2)
  if (volume < 10) return volume.toFixed(1)
  return Math.round(volume).toString()
}

// 切换排序
const toggleSort = (field) => {
  if (sortBy.value === field) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = field
    sortDirection.value = 'desc'
  }
}

// 获取排序图标
const getSortIcon = (field) => {
  if (sortBy.value !== field) return '↕️'
  return sortDirection.value === 'asc' ? '↑' : '↓'
}

// 全局最大交易量
const globalMaxVolume = computed(() => {
  let max = 0
  filteredAndSortedTokens.value.forEach(stat => {
    stat.volumes.forEach(v => {
      if (v !== null && v > max) max = v
    })
  })
  return max
})

// 切换平台选择
const togglePlatform = (platform) => {
  const index = selectedPlatforms.value.indexOf(platform)
  if (index > -1) {
    selectedPlatforms.value.splice(index, 1)
  } else {
    selectedPlatforms.value.push(platform)
  }
}

// 全选/取消全选平台
const toggleAllPlatforms = () => {
  if (selectedPlatforms.value.length === allPlatforms.value.length) {
    selectedPlatforms.value = []
  } else {
    selectedPlatforms.value = [...allPlatforms.value]
  }
}

// 初始化
onMounted(() => {
  // 默认全选平台
  selectedPlatforms.value = [...allPlatforms.value]
})
</script>

<template>
  <div class="heatmap-viewer">
    <div class="heatmap-header">
      <h2>Token交易量热力图</h2>
      <div class="header-info">
        <span>数据天数: {{ props.chartData?.dates?.length || 0 }}</span>
        <span>Token总数: {{ tokenStats.length }}</span>
        <span>显示: {{ filteredAndSortedTokens.length }}</span>
      </div>
    </div>

    <div class="heatmap-controls">
      <div class="control-row">
        <div class="control-group">
          <label>搜索Token:</label>
          <input 
            type="text" 
            v-model="searchQuery"
            placeholder="输入Token名称..."
            class="search-input"
          >
        </div>

        <div class="control-group">
          <label>显示数量:</label>
          <select v-model.number="showTopN" class="select-input">
            <option :value="10">前10</option>
            <option :value="20">前20</option>
            <option :value="30">前30</option>
            <option :value="50">前50</option>
            <option :value="100">前100</option>
            <option :value="tokenStats.length">全部 ({{ tokenStats.length }})</option>
          </select>
        </div>

        <div class="control-group">
          <label>排序方式:</label>
          <select v-model="sortBy" class="select-input">
            <option value="appearance">出现次数</option>
            <option value="avgVolume">平均交易量</option>
            <option value="maxVolume">最大交易量</option>
            <option value="name">名称</option>
          </select>
        </div>

        <div class="control-group">
          <label>配色方案:</label>
          <select v-model="colorScheme" class="select-input">
            <option value="volume">蓝色渐变</option>
            <option value="change">绿色渐变</option>
          </select>
        </div>
      </div>

      <div class="control-row">
        <div class="control-group">
          <label>最小交易量:</label>
          <div class="volume-filter">
            <input 
              type="range" 
              v-model.number="minVolume"
              min="0"
              max="10"
              step="0.1"
              class="volume-slider"
            >
            <span class="volume-value">${{ minVolume.toFixed(1) }}M ({{ (minVolume * 1000).toFixed(0) }}K)</span>
          </div>
        </div>

        <div class="control-group">
          <label>
            平台过滤 ({{ selectedPlatforms.length }}/{{ allPlatforms.length }}):
          </label>
          <button @click="toggleAllPlatforms" class="btn-toggle">
            {{ selectedPlatforms.length === allPlatforms.length ? '取消全选' : '全选平台' }}
          </button>
        </div>
      </div>

      <div class="platform-filter" v-if="allPlatforms.length > 0">
        <div 
          v-for="platform in allPlatforms" 
          :key="platform"
          class="platform-tag"
          :class="{ selected: selectedPlatforms.includes(platform) }"
          @click="togglePlatform(platform)"
        >
          {{ platform }}
        </div>
      </div>
    </div>

    <div class="legend">
      <span class="legend-label">交易量图例（百万美元）:</span>
      <div class="legend-gradient">
        <span class="legend-min">低</span>
        <div class="legend-bar" :style="{ 
          background: colorScheme === 'volume' 
            ? 'linear-gradient(to right, #f5f5f5, #8080ff, #0000ff)' 
            : 'linear-gradient(to right, #f5f5f5, #90ee90, #32cd32)'
        }"></div>
        <span class="legend-max">高</span>
      </div>
    </div>

    <div class="heatmap-wrapper">
      <table class="heatmap-table">
        <thead>
          <tr>
            <th class="sticky-col token-col" @click="toggleSort('name')">
              Token {{ getSortIcon('name') }}
            </th>
            <th class="stats-col" @click="toggleSort('appearance')">
              出现次数 {{ getSortIcon('appearance') }}
            </th>
            <th class="stats-col" @click="toggleSort('avgVolume')">
              平均量 {{ getSortIcon('avgVolume') }}
            </th>
            <th class="stats-col" @click="toggleSort('maxVolume')">
              最大量 {{ getSortIcon('maxVolume') }}
            </th>
            <th 
              v-for="(date, index) in timeLabels" 
              :key="index"
              class="date-col"
            >
              {{ date }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="stat in filteredAndSortedTokens" :key="stat.token">
            <td class="sticky-col token-col token-name">
              {{ stat.token }}
            </td>
            <td class="stats-col">
              {{ stat.appearance }} ({{ stat.appearanceRate }}%)
            </td>
            <td class="stats-col">
              ${{ stat.avgVolume.toFixed(1) }}M
            </td>
            <td class="stats-col">
              ${{ stat.maxVolume.toFixed(1) }}M
            </td>
            <td 
              v-for="(volume, index) in stat.volumes" 
              :key="index"
              class="volume-cell"
              :style="{
                backgroundColor: getCellColor(volume, globalMaxVolume),
                color: getTextColor(volume, globalMaxVolume)
              }"
              :title="`${stat.token} - ${timeLabels[index]}: ${volume ? '$' + volume.toFixed(2) + 'M' : '无数据'}`"
            >
              {{ formatVolume(volume) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.heatmap-viewer {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--bg-color);
}

.heatmap-header {
  padding: 12px 15px;
  border-bottom: 2px solid var(--border-color);
  flex-shrink: 0;
}

.heatmap-header h2 {
  margin: 0 0 8px 0;
  color: var(--text-color);
  font-size: 18px;
}

.header-info {
  display: flex;
  gap: 15px;
  font-size: 12px;
  color: var(--text-color);
  opacity: 0.8;
}

.heatmap-controls {
  padding: 10px 15px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
}

.control-row {
  display: flex;
  gap: 20px;
  align-items: center;
  flex-wrap: wrap;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.control-group label {
  font-size: 13px;
  color: var(--text-color);
  white-space: nowrap;
}

.search-input,
.select-input {
  padding: 6px 10px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background-color: var(--bg-color);
  color: var(--text-color);
  font-size: 13px;
}

.search-input {
  width: 200px;
}

.select-input {
  cursor: pointer;
}

.volume-filter {
  display: flex;
  align-items: center;
  gap: 10px;
}

.volume-slider {
  width: 200px;
  cursor: pointer;
}

.volume-value {
  font-size: 13px;
  color: var(--text-color);
  font-weight: 600;
  min-width: 120px;
}

.btn-toggle {
  padding: 6px 12px;
  background-color: #1976d2;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: background-color 0.2s;
}

.btn-toggle:hover {
  background-color: #1565c0;
}

.platform-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 5px;
}

.platform-tag {
  padding: 6px 12px;
  border: 2px solid var(--border-color);
  border-radius: 20px;
  background-color: var(--bg-color);
  color: var(--text-color);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}

.platform-tag:hover {
  background-color: var(--hover-color);
  border-color: #1976d2;
}

.platform-tag.selected {
  background-color: #1976d2;
  border-color: #1976d2;
  color: white;
  font-weight: 600;
}

.legend {
  padding: 8px 15px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.legend-label {
  font-size: 11px;
  color: var(--text-color);
  white-space: nowrap;
}

.legend-gradient {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  max-width: 300px;
}

.legend-bar {
  flex: 1;
  height: 16px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
}

.legend-min,
.legend-max {
  font-size: 10px;
  color: var(--text-color);
}

.heatmap-wrapper {
  flex: 1;
  overflow: auto;
  padding: 0;
  min-height: 0;
  max-height: 500px;
  position: relative;
}

.heatmap-table {
  width: max-content;
  border-collapse: collapse;
  font-size: 11px;
}

.heatmap-table thead {
  position: sticky;
  top: 0;
  z-index: 20;
  background-color: var(--bg-color);
}

.heatmap-table th {
  padding: 8px 6px;
  text-align: center;
  font-weight: bold;
  color: var(--text-color);
  border: 1px solid var(--border-color);
  background-color: var(--sidebar-bg);
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
  font-size: 10px;
}

.heatmap-table th:hover {
  background-color: var(--hover-color);
}

.sticky-col {
  position: sticky;
  left: 0;
  z-index: 10;
  background-color: var(--bg-color);
}

.heatmap-table thead .sticky-col {
  z-index: 30;
  background-color: var(--sidebar-bg);
}

.token-col {
  min-width: 100px;
  max-width: 100px;
  text-align: left !important;
}

.token-name {
  font-weight: 600;
  color: var(--text-color);
  background-color: var(--bg-color);
  font-size: 11px;
}

.stats-col {
  min-width: 90px;
  background-color: var(--bg-color);
  position: sticky;
  z-index: 10;
  font-size: 10px;
}

.stats-col:nth-child(2) {
  left: 100px;
}

.stats-col:nth-child(3) {
  left: 190px;
}

.stats-col:nth-child(4) {
  left: 280px;
}

.heatmap-table thead .stats-col {
  z-index: 30;
  background-color: var(--sidebar-bg);
}

.date-col {
  min-width: 55px;
  font-size: 9px;
}

.volume-cell {
  text-align: center;
  padding: 6px 3px;
  border: 1px solid var(--border-color);
  font-size: 10px;
  transition: all 0.2s;
}

.volume-cell:hover {
  transform: scale(1.1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  z-index: 5;
  border: 2px solid #1976d2;
}

.heatmap-table td {
  border: 1px solid var(--border-color);
  padding: 6px;
}

/* 滚动条样式 */
.heatmap-wrapper::-webkit-scrollbar {
  width: 12px;
  height: 12px;
}

.heatmap-wrapper::-webkit-scrollbar-track {
  background: var(--sidebar-bg);
}

.heatmap-wrapper::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 6px;
}

.heatmap-wrapper::-webkit-scrollbar-thumb:hover {
  background: var(--hover-color);
}

.heatmap-wrapper::-webkit-scrollbar-corner {
  background: var(--sidebar-bg);
}

@media (max-width: 768px) {
  .control-row {
    flex-direction: column;
    align-items: stretch;
  }
  
  .control-group {
    flex-direction: column;
    align-items: stretch;
  }
  
  .search-input,
  .volume-slider {
    width: 100%;
  }
}
</style>

