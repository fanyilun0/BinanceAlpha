<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DataZoomComponent,
  ToolboxComponent
} from 'echarts/components'

// 注册 ECharts 组件
use([
  CanvasRenderer,
  LineChart,
  BarChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DataZoomComponent,
  ToolboxComponent
])

const props = defineProps({
  chartData: {
    type: Object,
    required: true
  }
})

const selectedTokens = ref([])
const selectedPlatforms = ref([])
const minVolume = ref(0.1) // 默认100K = 0.1M
const startDateIndex = ref(0)
const endDateIndex = ref(0)
const displayDays = ref(30) // 默认显示天数

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
    '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
    '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#FF6B6B',
    '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD',
    '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8B500',
    '#00CED1', '#FF69B4', '#32CD32', '#FF4500', '#9370DB',
    '#20B2AA', '#FF6347', '#4169E1', '#8B4513', '#2E8B57'
  ]
  return colors[index % colors.length]
}

// ECharts 配置选项
const chartOption = computed(() => {
  if (!props.chartData || !props.chartData.tokens || selectedTokens.value.length === 0) {
    return {
      title: {
        text: '暂无数据',
        subtext: '请选择平台后查看数据',
        left: 'center',
        top: 'middle',
        textStyle: {
          color: '#999',
          fontSize: 18
        },
        subtextStyle: {
          color: '#bbb',
          fontSize: 14
        }
      }
    }
  }

  const start = startDateIndex.value
  const end = endDateIndex.value || allDates.value.length - 1

  const series = selectedTokens.value.map((token, index) => {
    const tokenData = props.chartData.tokens[token]
    const volumes = tokenData?.volumes || tokenData || []
    const filteredVolumes = volumes.slice(start, end + 1)
    const color = generateColor(index)
    
    return {
      name: token,
      type: 'line',
      data: filteredVolumes,
      smooth: true,
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: {
        width: 2,
        color: color
      },
      itemStyle: {
        color: color
      },
      emphasis: {
        focus: 'series'
      }
    }
  })

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        label: {
          backgroundColor: '#6a7985'
        }
      },
      backgroundColor: 'rgba(0, 0, 0, 0.85)',
      borderColor: '#555',
      borderWidth: 1,
      textStyle: {
        color: '#fff',
        fontSize: 12
      },
      formatter: function(params) {
        let result = `<div style="font-weight: bold; margin-bottom: 8px; font-size: 13px; border-bottom: 1px solid #555; padding-bottom: 5px;">${params[0].axisValue}</div>`
        params.forEach(param => {
          if (param.value !== null && param.value !== undefined) {
            result += `<div style="margin: 3px 0; display: flex; align-items: center;">
              <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background-color:${param.color};margin-right:8px;"></span>
              <span style="flex: 1;">${param.seriesName}</span>
              <span style="font-weight: bold; margin-left: 10px;">$${param.value.toFixed(2)}M</span>
            </div>`
          }
        })
        return result
      }
    },
    legend: {
      type: 'scroll',
      orient: 'vertical',
      right: 10,
      top: 60,
      bottom: 60,
      padding: [5, 10],
      itemGap: 8,
      itemWidth: 20,
      itemHeight: 12,
      textStyle: {
        fontSize: 11
      },
      pageButtonItemGap: 5,
      pageButtonGap: 10,
      pageIconSize: 12,
      pageTextStyle: {
        fontSize: 11
      },
      selector: [
        { type: 'all', title: '全选' },
        { type: 'inverse', title: '反选' }
      ],
      selectorLabel: {
        fontSize: 11
      }
    },
    grid: {
      left: 60,
      right: 180,
      bottom: 80,
      top: 60,
      containLabel: false
    },
    toolbox: {
      feature: {
        dataZoom: {
          yAxisIndex: 'none',
          title: { zoom: '区域缩放', back: '还原' }
        },
        restore: { title: '重置' },
        saveAsImage: {
          name: 'token_volume_chart',
          title: '保存图片'
        }
      },
      right: 180,
      top: 10
    },
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100
      },
      {
        type: 'slider',
        start: 0,
        end: 100,
        height: 25,
        bottom: 20,
        borderColor: 'transparent',
        backgroundColor: '#f5f5f5',
        fillerColor: 'rgba(25, 118, 210, 0.2)',
        handleStyle: {
          color: '#1976d2'
        },
        textStyle: {
          fontSize: 11
        }
      }
    ],
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: timeLabels.value,
      axisLabel: {
        rotate: 45,
        interval: 'auto',
        fontSize: 10,
        color: '#666'
      },
      axisLine: {
        lineStyle: {
          color: '#ddd'
        }
      }
    },
    yAxis: {
      type: 'value',
      position: 'left',
      axisLabel: {
        formatter: '${value}M',
        fontSize: 10,
        color: '#666'
      },
      splitLine: {
        lineStyle: {
          type: 'dashed',
          color: '#eee'
        }
      },
      axisLine: {
        show: false
      }
    },
    series: series
  }
})

// 切换平台选择
const togglePlatform = (platform) => {
  const index = selectedPlatforms.value.indexOf(platform)
  if (index > -1) {
    selectedPlatforms.value.splice(index, 1)
  } else {
    selectedPlatforms.value.push(platform)
  }
  // 重新选择所有符合条件的token
  selectAllTokens()
}

// 全选/取消全选平台
const toggleAllPlatforms = () => {
  if (selectedPlatforms.value.length === allPlatforms.value.length) {
    selectedPlatforms.value = []
  } else {
    selectedPlatforms.value = [...allPlatforms.value]
  }
  selectAllTokens()
}

// 选择所有符合条件的token
const selectAllTokens = () => {
  selectedTokens.value = [...availableTokens.value]
}

// 重置日期范围
const resetDateRange = () => {
  startDateIndex.value = 0
  endDateIndex.value = allDates.value.length - 1
  displayDays.value = allDates.value.length
}

// 设置最近N天
const setRecentDays = (days) => {
  const totalDays = allDates.value.length
  startDateIndex.value = Math.max(0, totalDays - days)
  endDateIndex.value = totalDays - 1
  displayDays.value = days
}

// 监听平台变化，自动更新token选择
watch(selectedPlatforms, () => {
  selectAllTokens()
}, { deep: true })

// 监听最小交易量变化
watch(minVolume, () => {
  selectAllTokens()
})

// 初始化时默认选择 BSC 和 Base 链
onMounted(() => {
  // 默认选择 BSC 和 Base 平台
  const defaultPlatforms = ['BNB', 'BASE']
  selectedPlatforms.value = allPlatforms.value.filter(p => 
    defaultPlatforms.includes(p.toUpperCase())
  )
  
  // 如果没有找到这些平台，则不选择任何平台
  // 设置日期范围为最近30天
  setRecentDays(30)
  
  // 选择所有符合条件的token
  selectAllTokens()
})
</script>

<template>
  <div class="volume-chart-viewer">
    <!-- 顶部控制栏 -->
    <div class="chart-toolbar">
      <!-- 左侧：统计信息 -->
      <div class="toolbar-stats">
        <div class="stat-item">
          <span class="stat-label">数据范围</span>
          <span class="stat-value">{{ dateRangeText }}</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item">
          <span class="stat-label">显示天数</span>
          <span class="stat-value highlight">{{ timeLabels.length }} 天</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item">
          <span class="stat-label">代币数量</span>
          <span class="stat-value highlight">{{ selectedTokens.length }} 个</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item">
          <span class="stat-label">总数据量</span>
          <span class="stat-value">{{ allDates.length }} 天可用</span>
        </div>
      </div>

      <!-- 右侧：日期快捷按钮 -->
      <div class="toolbar-actions">
        <div class="date-buttons">
          <button 
            @click="setRecentDays(7)" 
            class="date-btn"
            :class="{ active: displayDays === 7 }"
          >7天</button>
          <button 
            @click="setRecentDays(30)" 
            class="date-btn"
            :class="{ active: displayDays === 30 }"
          >30天</button>
          <button 
            @click="setRecentDays(90)" 
            class="date-btn"
            :class="{ active: displayDays === 90 }"
          >90天</button>
          <button 
            @click="resetDateRange" 
            class="date-btn"
            :class="{ active: displayDays === allDates.length }"
          >全部</button>
        </div>
      </div>
    </div>

    <!-- 过滤器区域 -->
    <div class="chart-filters">
      <!-- 最小交易量 -->
      <div class="filter-item">
        <span class="filter-label">最小交易量</span>
        <div class="volume-control">
          <input 
            type="range" 
            v-model.number="minVolume"
            min="0"
            max="10"
            step="0.1"
            class="volume-slider"
          >
          <span class="volume-value">${{ minVolume.toFixed(1) }}M</span>
        </div>
      </div>

      <div class="filter-divider"></div>

      <!-- 平台过滤 -->
      <div class="filter-item platforms">
        <span class="filter-label">
          平台筛选
          <button @click="toggleAllPlatforms" class="toggle-all-btn">
            {{ selectedPlatforms.length === allPlatforms.length ? '清空' : '全选' }}
          </button>
        </span>
        <div class="platform-tags">
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
    </div>

    <!-- 图表区域 -->
    <div class="chart-content">
      <v-chart 
        class="chart" 
        :option="chartOption" 
        autoresize
      />
    </div>
  </div>
</template>

<style scoped>
.volume-chart-viewer {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--bg-color);
}

/* 顶部工具栏 */
.chart-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  flex-shrink: 0;
}

.toolbar-stats {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-label {
  font-size: 10px;
  opacity: 0.8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-value {
  font-size: 13px;
  font-weight: 600;
}

.stat-value.highlight {
  color: #ffd700;
}

.stat-divider {
  width: 1px;
  height: 30px;
  background-color: rgba(255, 255, 255, 0.3);
  margin: 0 12px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 15px;
}

.date-buttons {
  display: flex;
  gap: 6px;
}

.date-btn {
  padding: 6px 14px;
  background-color: rgba(255, 255, 255, 0.15);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 20px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.2s;
}

.date-btn:hover {
  background-color: rgba(255, 255, 255, 0.25);
}

.date-btn.active {
  background-color: white;
  color: #667eea;
  border-color: white;
  font-weight: 600;
}

/* 过滤器区域 */
.chart-filters {
  display: flex;
  align-items: center;
  padding: 10px 20px;
  background-color: var(--sidebar-bg);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
  gap: 15px;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.filter-item.platforms {
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.filter-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-color);
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 8px;
}

.toggle-all-btn {
  padding: 2px 8px;
  background-color: transparent;
  color: #1976d2;
  border: 1px solid #1976d2;
  border-radius: 10px;
  cursor: pointer;
  font-size: 10px;
  transition: all 0.2s;
}

.toggle-all-btn:hover {
  background-color: #1976d2;
  color: white;
}

.filter-divider {
  width: 1px;
  height: 40px;
  background-color: var(--border-color);
}

.volume-control {
  display: flex;
  align-items: center;
  gap: 10px;
}

.volume-slider {
  width: 120px;
  cursor: pointer;
  accent-color: #1976d2;
}

.volume-value {
  font-size: 12px;
  font-weight: 600;
  color: #1976d2;
  min-width: 50px;
}

.platform-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.platform-tag {
  padding: 4px 12px;
  border: 1px solid var(--border-color);
  border-radius: 15px;
  background-color: var(--bg-color);
  color: var(--text-color);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}

.platform-tag:hover {
  border-color: #1976d2;
  color: #1976d2;
}

.platform-tag.selected {
  background-color: #1976d2;
  border-color: #1976d2;
  color: white;
  font-weight: 500;
}

/* 图表区域 */
.chart-content {
  flex: 1;
  overflow: hidden;
  min-height: 0;
  padding: 10px;
}

.chart {
  width: 100%;
  height: 100%;
  min-height: 400px;
}

/* 响应式 */
@media (max-width: 1024px) {
  .toolbar-stats {
    flex-wrap: wrap;
  }
  
  .stat-divider {
    display: none;
  }
  
  .stat-item {
    flex-direction: row;
    gap: 6px;
  }
  
  .stat-label {
    font-size: 9px;
  }
  
  .stat-value {
    font-size: 11px;
  }
}

@media (max-width: 768px) {
  .chart-toolbar {
    flex-direction: column;
    gap: 10px;
    padding: 10px 15px;
  }
  
  .chart-filters {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
    padding: 10px 15px;
  }
  
  .filter-divider {
    width: 100%;
    height: 1px;
  }
  
  .filter-item {
    width: 100%;
  }
  
  .volume-slider {
    flex: 1;
    width: auto;
  }
}
</style>
