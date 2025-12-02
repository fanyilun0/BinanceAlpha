<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale
} from 'chart.js'
import { Line } from 'vue-chartjs'

// 注册 Chart.js 组件
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale
)

const props = defineProps({
  chartData: {
    type: Object,
    required: true
  }
})

const selectedTokens = ref([])
const searchQuery = ref('')
const isLoading = ref(false)
const selectedPlatforms = ref([])
const minVolume = ref(0.1) // 默认100K = 0.1M
const startDateIndex = ref(0)
const endDateIndex = ref(0)

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

// 可用的token列表（从数据中提取，应用过滤）
const availableTokens = computed(() => {
  if (!props.chartData || !props.chartData.tokens) return []
  
  let tokens = Object.entries(props.chartData.tokens)
  
  // 按平台过滤
  if (selectedPlatforms.value.length > 0) {
    tokens = tokens.filter(([_, data]) => {
      const platforms = data.platforms || []
      return platforms.some(p => selectedPlatforms.value.includes(p))
    })
  }
  
  // 按最小交易量过滤
  tokens = tokens.filter(([_, data]) => {
    const volumes = data.volumes || data
    const maxVolume = Math.max(...volumes.filter(v => v !== null && v > 0))
    return maxVolume >= minVolume.value
  })
  
  return tokens.map(([symbol]) => symbol).sort()
})

// 过滤后的token列表
const filteredTokens = computed(() => {
  if (!searchQuery.value) return availableTokens.value
  const query = searchQuery.value.toLowerCase()
  return availableTokens.value.filter(token => 
    token.toLowerCase().includes(query)
  )
})

// 所有日期
const allDates = computed(() => {
  if (!props.chartData || !props.chartData.dates) return []
  return props.chartData.dates
})

// 过滤后的时间标签（根据日期范围）
const timeLabels = computed(() => {
  if (!allDates.value.length) return []
  const start = startDateIndex.value
  const end = endDateIndex.value || allDates.value.length - 1
  return allDates.value.slice(start, end + 1).map(date => {
    const d = new Date(date)
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })
})

// 日期范围文本
const dateRangeText = computed(() => {
  if (!allDates.value.length) return ''
  const start = allDates.value[startDateIndex.value]
  const end = allDates.value[endDateIndex.value || allDates.value.length - 1]
  return `${start} 至 ${end}`
})

// 生成随机颜色
const generateColor = (index) => {
  const colors = [
    '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
    '#FF9F40', '#FF6384', '#C9CBCF', '#4BC0C0', '#FF6384',
    '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40',
    '#E7E9ED', '#71B37C', '#EC932F', '#BA55D3', '#FF1493',
    '#00CED1', '#FFD700', '#ADFF2F', '#FF69B4', '#87CEEB',
    '#FFA07A', '#98FB98', '#DDA0DD', '#F0E68C', '#B0C4DE'
  ]
  return colors[index % colors.length]
}

// 图表数据（根据日期范围过滤）
const chartDataFormatted = computed(() => {
  if (!props.chartData || !props.chartData.tokens || selectedTokens.value.length === 0) {
    return {
      labels: [],
      datasets: []
    }
  }

  const start = startDateIndex.value
  const end = endDateIndex.value || allDates.value.length - 1

  const datasets = selectedTokens.value.map((token, index) => {
    const tokenData = props.chartData.tokens[token]
    const volumes = tokenData?.volumes || tokenData || []
    const filteredVolumes = volumes.slice(start, end + 1)
    const color = generateColor(index)
    
    return {
      label: token,
      data: filteredVolumes,
      borderColor: color,
      backgroundColor: color + '20',
      borderWidth: 2,
      tension: 0.4,
      pointRadius: 2,
      pointHoverRadius: 4,
      fill: false
    }
  })

  return {
    labels: timeLabels.value,
    datasets: datasets
  }
})

// 图表配置
const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: {
    mode: 'index',
    intersect: false,
  },
  plugins: {
    legend: {
      position: 'top',
      align: 'start',
      labels: {
        color: getComputedStyle(document.documentElement).getPropertyValue('--text-color') || '#24292e',
        font: {
          size: 11
        },
        usePointStyle: true,
        padding: 10,
        boxWidth: 8,
        boxHeight: 8
      }
    },
    title: {
      display: false
    },
    tooltip: {
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      titleColor: '#fff',
      bodyColor: '#fff',
      borderColor: '#666',
      borderWidth: 1,
      padding: 10,
      displayColors: true,
      titleFont: {
        size: 12
      },
      bodyFont: {
        size: 11
      },
      callbacks: {
        label: function(context) {
          let label = context.dataset.label || ''
          if (label) {
            label += ': '
          }
          if (context.parsed.y !== null) {
            label += '$' + context.parsed.y.toFixed(2) + 'M'
          }
          return label
        }
      }
    }
  },
  scales: {
    x: {
      display: true,
      position: 'bottom',
      title: {
        display: false
      },
      ticks: {
        color: getComputedStyle(document.documentElement).getPropertyValue('--text-color') || '#24292e',
        font: {
          size: 10
        },
        maxRotation: 0,
        minRotation: 0,
        autoSkip: true,
        maxTicksLimit: 20
      },
      grid: {
        display: false
      }
    },
    y: {
      display: true,
      position: 'right',
      title: {
        display: false
      },
      ticks: {
        color: getComputedStyle(document.documentElement).getPropertyValue('--text-color') || '#24292e',
        font: {
          size: 10
        },
        callback: function(value) {
          return '$' + value.toFixed(0) + 'M'
        }
      },
      grid: {
        color: getComputedStyle(document.documentElement).getPropertyValue('--border-color') || '#ddd',
        drawBorder: false
      }
    }
  }
}))

// 切换token选择
const toggleToken = (token) => {
  const index = selectedTokens.value.indexOf(token)
  if (index > -1) {
    selectedTokens.value.splice(index, 1)
  } else {
    selectedTokens.value.push(token)
  }
}

// 选择前N个token
const selectTopN = (n) => {
  selectedTokens.value = availableTokens.value.slice(0, n)
}

// 全选
const selectAll = () => {
  selectedTokens.value = [...availableTokens.value]
}

// 清空选择
const clearSelection = () => {
  selectedTokens.value = []
}

// 切换平台选择
const togglePlatform = (platform) => {
  const index = selectedPlatforms.value.indexOf(platform)
  if (index > -1) {
    selectedPlatforms.value.splice(index, 1)
  } else {
    selectedPlatforms.value.push(platform)
  }
  // 重新应用token选择
  updateTokenSelection()
}

// 全选/取消全选平台
const toggleAllPlatforms = () => {
  if (selectedPlatforms.value.length === allPlatforms.value.length) {
    selectedPlatforms.value = []
  } else {
    selectedPlatforms.value = [...allPlatforms.value]
  }
  updateTokenSelection()
}

// 更新token选择（在过滤条件改变时）
const updateTokenSelection = () => {
  // 移除不再符合过滤条件的token
  selectedTokens.value = selectedTokens.value.filter(token => 
    availableTokens.value.includes(token)
  )
}

// 重置日期范围
const resetDateRange = () => {
  startDateIndex.value = 0
  endDateIndex.value = allDates.value.length - 1
}

// 设置最近N天
const setRecentDays = (days) => {
  const totalDays = allDates.value.length
  startDateIndex.value = Math.max(0, totalDays - days)
  endDateIndex.value = totalDays - 1
}

// 初始化时全选所有token，设置默认最小交易量为100K
onMounted(() => {
  // 默认全选平台
  selectedPlatforms.value = [...allPlatforms.value]
  // 设置日期范围为全部
  endDateIndex.value = allDates.value.length - 1
  // 默认全选token
  if (availableTokens.value.length > 0) {
    selectedTokens.value = [...availableTokens.value]
  }
})
</script>

<template>
  <div class="volume-chart-viewer">
    <div class="chart-header">
      <div class="header-title">
        <h2>Token交易量趋势分析</h2>
        <div class="chart-info">
          <span>数据范围: {{ timeLabels.length }} / {{ allDates.length }} 天</span>
          <span>可用Token: {{ availableTokens.length }} 个</span>
          <span>已选择: {{ selectedTokens.length }} 个</span>
        </div>
      </div>
      
      <div class="date-range-selector">
        <label class="control-label">日期范围:</label>
        <div class="date-range-controls">
          <button @click="setRecentDays(7)" class="btn-date">最近7天</button>
          <button @click="setRecentDays(30)" class="btn-date">最近30天</button>
          <button @click="setRecentDays(90)" class="btn-date">最近90天</button>
          <button @click="resetDateRange" class="btn-date">全部</button>
        </div>
        <div class="date-range-sliders">
          <div class="slider-group">
            <label>起始:</label>
            <input 
              type="range" 
              v-model.number="startDateIndex"
              :min="0"
              :max="allDates.length - 1"
              class="date-slider"
            >
            <span class="date-label">{{ allDates[startDateIndex] }}</span>
          </div>
          <div class="slider-group">
            <label>结束:</label>
            <input 
              type="range" 
              v-model.number="endDateIndex"
              :min="startDateIndex"
              :max="allDates.length - 1"
              class="date-slider"
            >
            <span class="date-label">{{ allDates[endDateIndex] }}</span>
          </div>
        </div>
        <div class="date-range-display">
          {{ dateRangeText }}
        </div>
      </div>
    </div>

    <div class="chart-controls">
      <div class="control-row">
        <div class="control-group">
          <label class="control-label">快速选择:</label>
          <div class="quick-select">
            <button @click="selectTopN(5)" class="btn-small">前5</button>
            <button @click="selectTopN(10)" class="btn-small">前10</button>
            <button @click="selectTopN(20)" class="btn-small">前20</button>
            <button @click="selectTopN(30)" class="btn-small">前30</button>
            <button @click="selectAll" class="btn-small btn-success">全选</button>
            <button @click="clearSelection" class="btn-small btn-clear">清空</button>
          </div>
        </div>
        
        <div class="control-group">
          <label class="control-label">搜索Token:</label>
          <input 
            type="text" 
            v-model="searchQuery"
            placeholder="输入Token名称..."
            class="search-input"
          >
        </div>
      </div>

      <div class="control-row">
        <div class="control-group">
          <label class="control-label">最小交易量:</label>
          <div class="volume-filter">
            <input 
              type="range" 
              v-model.number="minVolume"
              min="0"
              max="10"
              step="0.1"
              class="volume-slider"
              @input="updateTokenSelection"
            >
            <span class="volume-value">${{ minVolume.toFixed(1) }}M ({{ (minVolume * 1000).toFixed(0) }}K)</span>
          </div>
        </div>

        <div class="control-group">
          <label class="control-label">
            平台过滤 ({{ selectedPlatforms.length }}/{{ allPlatforms.length }}):
          </label>
          <button @click="toggleAllPlatforms" class="btn-small">
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

    <div class="chart-content">
      <div class="token-selector">
        <div class="token-list">
          <div 
            v-for="token in filteredTokens" 
            :key="token"
            class="token-item"
            :class="{ selected: selectedTokens.includes(token) }"
            @click="toggleToken(token)"
          >
            <span class="token-checkbox">
              {{ selectedTokens.includes(token) ? '☑' : '☐' }}
            </span>
            <span class="token-name">{{ token }}</span>
          </div>
        </div>
      </div>

      <div class="chart-wrapper">
        <div v-if="selectedTokens.length === 0" class="no-selection">
          请从左侧选择Token以查看交易量趋势
        </div>
        <Line 
          v-else
          :data="chartDataFormatted" 
          :options="chartOptions"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.volume-chart-viewer {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chart-header {
  padding: 12px 15px;
  border-bottom: 2px solid var(--border-color);
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}

.header-title {
  flex: 1;
  min-width: 250px;
}

.chart-header h2 {
  margin: 0 0 8px 0;
  color: var(--text-color);
  font-size: 18px;
}

.chart-info {
  display: flex;
  gap: 15px;
  font-size: 12px;
  color: var(--text-color);
  opacity: 0.8;
}

.date-range-selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 12px;
  background-color: var(--sidebar-bg);
  border-radius: 6px;
  border: 1px solid var(--border-color);
}

.date-range-controls {
  display: flex;
  gap: 6px;
}

.btn-date {
  padding: 4px 10px;
  background-color: #1976d2;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
  transition: background-color 0.2s;
}

.btn-date:hover {
  background-color: #1565c0;
}

.date-range-sliders {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.slider-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.slider-group label {
  font-size: 11px;
  color: var(--text-color);
  min-width: 35px;
}

.date-slider {
  flex: 1;
  min-width: 150px;
  cursor: pointer;
}

.date-label {
  font-size: 11px;
  color: var(--text-color);
  font-weight: 600;
  min-width: 80px;
}

.date-range-display {
  font-size: 11px;
  color: #1976d2;
  font-weight: 600;
  text-align: center;
  padding: 4px;
  background-color: var(--bg-color);
  border-radius: 4px;
}

.chart-controls {
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
  gap: 10px;
}

.control-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color);
  white-space: nowrap;
}

.quick-select {
  display: flex;
  gap: 8px;
}

.btn-small {
  padding: 6px 12px;
  background-color: #1976d2;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: background-color 0.2s;
}

.btn-small:hover {
  background-color: #1565c0;
}

.btn-success {
  background-color: #4caf50;
}

.btn-success:hover {
  background-color: #45a049;
}

.btn-clear {
  background-color: #f44336;
}

.btn-clear:hover {
  background-color: #d32f2f;
}

.search-input {
  width: 200px;
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background-color: var(--bg-color);
  color: var(--text-color);
  box-sizing: border-box;
  font-size: 13px;
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

.chart-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.token-selector {
  width: 220px;
  border-right: 1px solid var(--border-color);
  overflow-y: auto;
  flex-shrink: 0;
}

.token-list {
  padding: 10px 0;
}

.token-item {
  padding: 6px 12px;
  cursor: pointer;
  transition: background-color 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
  user-select: none;
}

.token-item:hover {
  background-color: var(--hover-color);
}

.token-item.selected {
  background-color: var(--active-color);
  color: #1976d2;
  font-weight: 600;
}

.token-checkbox {
  font-size: 14px;
}

.token-name {
  font-size: 12px;
}

.chart-wrapper {
  flex: 1;
  padding: 15px;
  overflow: auto;
  min-height: 0;
  position: relative;
}

.no-selection {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--text-color);
  font-size: 1.1em;
  opacity: 0.6;
  text-align: center;
}

/* 滚动条样式 */
.token-selector::-webkit-scrollbar,
.chart-wrapper::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.token-selector::-webkit-scrollbar-track,
.chart-wrapper::-webkit-scrollbar-track {
  background: var(--sidebar-bg);
}

.token-selector::-webkit-scrollbar-thumb,
.chart-wrapper::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 4px;
}

.token-selector::-webkit-scrollbar-thumb:hover,
.chart-wrapper::-webkit-scrollbar-thumb:hover {
  background: var(--hover-color);
}

@media (max-width: 768px) {
  .chart-content {
    flex-direction: column;
  }
  
  .token-selector {
    width: 100%;
    max-height: 200px;
    border-right: none;
    border-bottom: 1px solid var(--border-color);
  }
  
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

