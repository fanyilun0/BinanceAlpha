<script setup>
import { ref, computed, onMounted, watch, shallowRef } from 'vue'
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

// 获取 token 的最新交易量
const getLatestVolume = (volumes) => {
  if (!volumes) return 0
  for (let i = volumes.length - 1; i >= 0; i--) {
    if (volumes[i] !== null && volumes[i] !== undefined && volumes[i] > 0) {
      return volumes[i]
    }
  }
  return 0
}

// 获取 token 的交易量变化率（最近7天 vs 之前7天）
const getVolumeChange = (volumes) => {
  if (!volumes) return 0
  const validVolumes = volumes.filter(v => v !== null && v !== undefined && v > 0)
  if (validVolumes.length < 14) return 0
  
  const recent7 = validVolumes.slice(-7).reduce((a, b) => a + b, 0) / 7
  const prev7 = validVolumes.slice(-14, -7).reduce((a, b) => a + b, 0) / 7
  
  if (prev7 === 0) return 0
  return ((recent7 - prev7) / prev7) * 100
}

// 预计算的 Token 信息缓存
const tokenInfoCache = shallowRef([])

// 预计算 Token 信息
const preCalculateTokenInfo = () => {
  if (!rawChartData.value || !rawChartData.value.tokens) {
    tokenInfoCache.value = []
    return
  }

  const tokens = Object.entries(rawChartData.value.tokens)
  
  tokenInfoCache.value = tokens.map(([symbol, data]) => {
    const volumes = data.volumes || data
    // 计算最大交易量用于过滤
    const maxVolume = Math.max(...volumes.filter(v => v !== null && v > 0))
    const latestVolume = getLatestVolume(volumes)
    const volumeChange = getVolumeChange(volumes)
    
    // 计算热度得分: log(交易量 + 1) * (abs(变化率) + 1)
    // 这样既考虑了交易量大，也考虑了波动大
    const hotness = Math.log10(latestVolume + 1) * (Math.abs(volumeChange) + 1)

    return {
      symbol,
      name: data.name,
      platforms: data.platforms || [],
      volumes: volumes,
      maxVolume: maxVolume,
      latestVolume: latestVolume,
      volumeChange: volumeChange,
      hotness: hotness
    }
  })
}

// 使用 shallowRef 避免深度响应式带来的性能开销
const rawChartData = shallowRef(null)

// 监听 props.chartData 变化
watch(() => props.chartData, (newData) => {
  if (newData) {
    rawChartData.value = newData
    // 数据更新时重新计算所有 token 的预处理信息
    preCalculateTokenInfo()
  }
}, { immediate: true })

const selectedTokens = ref([])
const selectedPlatforms = ref([])
const minVolume = ref(1.0) // 默认 1M
const startDateIndex = ref(0)
const endDateIndex = ref(0)
const displayDays = ref(30) // 默认显示天数
const searchQuery = ref('') // 搜索关键词
const sortBy = ref('hotness') // 排序方式: hotness (热度), volume, name, change
const showTokenSelector = ref(true) // 是否显示 Token 选择器
const chartMode = ref('volume') // 图表模式: 'volume' (交易量), 'change' (变化率)

// 防抖后的搜索和筛选值
const debouncedSearchQuery = ref('')
const debouncedMinVolume = ref(1.0)

// 防抖处理
let searchTimeout = null
let volumeTimeout = null

watch(searchQuery, (newVal) => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    debouncedSearchQuery.value = newVal
  }, 300)
})

watch(minVolume, (newVal) => {
  if (volumeTimeout) clearTimeout(volumeTimeout)
  volumeTimeout = setTimeout(() => {
    debouncedMinVolume.value = newVal
  }, 300)
})

// 性能模式阈值
const PERFORMANCE_THRESHOLD = 20

// 所有平台列表
const allPlatforms = computed(() => {
  if (!tokenInfoCache.value.length) return []
  const platformsSet = new Set()
  tokenInfoCache.value.forEach(token => {
    token.platforms.forEach(p => platformsSet.add(p))
  })
  return Array.from(platformsSet).sort()
})

// 基础过滤：按平台和最小交易量
const baseFilteredTokens = computed(() => {
  let tokens = tokenInfoCache.value
  
  // 按平台过滤
  if (selectedPlatforms.value.length > 0) {
    tokens = tokens.filter(token => {
      return token.platforms.some(p => selectedPlatforms.value.includes(p))
    })
  }
  
  // 按最小交易量过滤 (使用防抖后的值)
  tokens = tokens.filter(token => {
    return token.maxVolume >= debouncedMinVolume.value
  })
  
  return tokens
})

// 排序后的 Token 列表
const sortedTokens = computed(() => {
  const tokens = [...baseFilteredTokens.value]
  
  if (sortBy.value === 'volume') {
    tokens.sort((a, b) => b.latestVolume - a.latestVolume)
  } else if (sortBy.value === 'name') {
    tokens.sort((a, b) => a.symbol.localeCompare(b.symbol))
  } else if (sortBy.value === 'change') {
    tokens.sort((a, b) => b.volumeChange - a.volumeChange)
  } else if (sortBy.value === 'hotness') {
    tokens.sort((a, b) => b.hotness - a.hotness)
  }
  
  return tokens
})

// 最终显示的 Token 列表 (应用搜索)
const filteredTokensWithInfo = computed(() => {
  if (!debouncedSearchQuery.value) return sortedTokens.value
  const query = debouncedSearchQuery.value.toLowerCase()
  return sortedTokens.value.filter(t => 
    t.symbol.toLowerCase().includes(query)
  )
})

// 可用的 token 符号列表
const availableTokens = computed(() => {
  return sortedTokens.value.map(t => t.symbol)
})

// Top N Tokens
const topTokens = computed(() => {
  return sortedTokens.value.slice(0, 10).map(t => t.symbol)
})

// 所有日期
const allDates = computed(() => {
  if (!rawChartData.value || !rawChartData.value.dates) return []
  return rawChartData.value.dates
})

// 过滤后的时间标签
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

// 是否启用性能模式
const isPerformanceMode = computed(() => {
  return selectedTokens.value.length > PERFORMANCE_THRESHOLD
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

// 计算日环比变化率数据
const calculateDailyChange = (volumes) => {
  if (!volumes || volumes.length < 2) return volumes.map(() => 0)
  
  const changes = []
  // 第一个点没有前一天，设为0
  changes.push(0)
  
  for (let i = 1; i < volumes.length; i++) {
    const curr = volumes[i]
    const prev = volumes[i-1]
    
    if (prev !== null && prev !== undefined && prev > 0 && curr !== null && curr !== undefined) {
      const change = ((curr - prev) / prev) * 100
      changes.push(change)
    } else {
      changes.push(0)
    }
  }
  return changes
}

// ECharts 配置选项
const chartOption = computed(() => {
  if (!rawChartData.value || !rawChartData.value.tokens || selectedTokens.value.length === 0) {
    return {
      title: {
        text: '请选择 Token',
        subtext: '从右侧列表中选择要显示的 Token',
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
  const isChangeMode = chartMode.value === 'change'

  const series = selectedTokens.value.map((token, index) => {
    // 从缓存中直接获取数据对象，避免重复查找
    const tokenInfo = tokenInfoCache.value.find(t => t.symbol === token)
    if (!tokenInfo) return null
    
    let displayData
    if (isChangeMode) {
      // 计算变化率数据
      const fullChangeData = calculateDailyChange(tokenInfo.volumes)
      displayData = fullChangeData.slice(start, end + 1)
    } else {
      // 原始交易量数据
      displayData = tokenInfo.volumes.slice(start, end + 1)
    }
    
    const color = generateColor(index)
    
    return {
      name: token,
      type: 'line',
      data: displayData,
      smooth: true,
      // 性能模式：关闭数据点图标
      symbol: isPerformanceMode.value ? 'none' : 'circle',
      symbolSize: isPerformanceMode.value ? 0 : 4,
      // 性能模式：开启降采样
      sampling: isPerformanceMode.value ? 'lttb' : undefined,
      lineStyle: {
        // 性能模式：线条变细
        width: isPerformanceMode.value ? 1.5 : 2,
        color: color
      },
      itemStyle: {
        color: color
      },
      emphasis: {
        focus: 'series'
      },
      // 变化率模式下不连接空数据
      connectNulls: !isChangeMode
    }
  }).filter(Boolean)

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
      // 优化 Tooltip：排序并限制显示数量
      formatter: function(params) {
        // 按数值降序排序
        const sortedParams = [...params].sort((a, b) => {
          const valA = a.value !== null && a.value !== undefined ? a.value : -Infinity
          const valB = b.value !== null && b.value !== undefined ? b.value : -Infinity
          return valB - valA
        })
        
        // 限制显示数量（最多 15 个）
        const maxDisplay = 15
        const displayParams = sortedParams.slice(0, maxDisplay)
        const remaining = sortedParams.length - maxDisplay
        
        let result = `<div style="font-weight: bold; margin-bottom: 8px; font-size: 13px; border-bottom: 1px solid #555; padding-bottom: 5px;">${params[0].axisValue}</div>`
        
        displayParams.forEach(param => {
          if (param.value !== null && param.value !== undefined) {
            let valueStr = ''
            let colorStyle = ''
            
            if (isChangeMode) {
              const val = param.value
              const sign = val > 0 ? '+' : ''
              valueStr = `${sign}${val.toFixed(2)}%`
              if (val > 0) colorStyle = 'color: #ff6b6b;'
              else if (val < 0) colorStyle = 'color: #4ecdc4;'
            } else {
              valueStr = `$${param.value.toFixed(2)}M`
            }
            
            result += `<div style="margin: 3px 0; display: flex; align-items: center;">
              <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background-color:${param.color};margin-right:8px;"></span>
              <span style="flex: 1; max-width: 100px; overflow: hidden; text-overflow: ellipsis;">${param.seriesName}</span>
              <span style="font-weight: bold; margin-left: 10px; ${colorStyle}">${valueStr}</span>
            </div>`
          }
        })
        
        if (remaining > 0) {
          result += `<div style="margin-top: 5px; color: #999; font-size: 11px; text-align: center;">...还有 ${remaining} 个 Token</div>`
        }
        
        return result
      }
    },
    legend: {
      show: true,
      type: 'scroll',
      top: 0,
      left: 60,
      right: showTokenSelector.value ? 280 : 20,
      textStyle: {
        color: '#666',
        fontSize: 11
      },
      pageIconColor: '#667eea',
      pageTextStyle: {
        color: '#666'
      }
    },
    grid: {
      left: 60,
      right: showTokenSelector.value ? 280 : 20,
      bottom: 80,
      top: 40,
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
          name: isChangeMode ? 'token_volume_change_chart' : 'token_volume_chart',
          title: '保存图片'
        }
      },
      right: showTokenSelector.value ? 290 : 30,
      top: 0
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
      type: isChangeMode ? 'value' : 'log', // 变化率用线性轴，交易量用对数轴
      logBase: 10,
      position: 'left',
      name: isChangeMode ? '24H 变化率 (%)' : '24H 交易量 (USD)',
      nameLocation: 'end',
      nameTextStyle: {
        align: 'right',
        padding: [0, 10, 0, 0]
      },
      axisLabel: {
        formatter: isChangeMode ? '{value}%' : '${value}M',
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

// 切换 Token 选择
const toggleToken = (symbol) => {
  const index = selectedTokens.value.indexOf(symbol)
  if (index > -1) {
    selectedTokens.value.splice(index, 1)
  } else {
    selectedTokens.value.push(symbol)
  }
}

// 选择 Top N 个 Token
const selectTopN = (n) => {
  selectedTokens.value = availableTokens.value.slice(0, n)
}

// 选择所有符合条件的 token
const selectAllTokens = () => {
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
  // 重新选择 Top 10
  selectTopN(10)
}

// 全选/取消全选平台
const toggleAllPlatforms = () => {
  if (selectedPlatforms.value.length === allPlatforms.value.length) {
    selectedPlatforms.value = []
  } else {
    selectedPlatforms.value = [...allPlatforms.value]
  }
  selectTopN(10)
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

// 格式化交易量显示
const formatVolume = (volume) => {
  if (volume >= 1) {
    return `$${volume.toFixed(1)}M`
  } else {
    return `$${(volume * 1000).toFixed(0)}K`
  }
}

// 格式化变化率显示
const formatChange = (change) => {
  if (change === 0) return '-'
  const sign = change > 0 ? '+' : ''
  return `${sign}${change.toFixed(1)}%`
}

// 监听平台变化，自动更新token选择
watch(selectedPlatforms, () => {
  // 保留已选中且仍然可用的 token
  selectedTokens.value = selectedTokens.value.filter(token => 
    availableTokens.value.includes(token)
  )
}, { deep: true })

// 监听最小交易量变化 (使用防抖后的值)
watch(debouncedMinVolume, () => {
  // 保留已选中且仍然可用的 token
  selectedTokens.value = selectedTokens.value.filter(token => 
    availableTokens.value.includes(token)
  )
})

// 初始化时默认选择 BSC 和 Base 链，仅选中 Top 10
onMounted(() => {
  // 默认选择 BSC 和 Base 平台
  const defaultPlatforms = ['BNB', 'BASE']
  // 等待数据加载完成后再筛选
  let unwatch = null
  unwatch = watch(allPlatforms, (platforms) => {
    if (platforms.length > 0) {
      selectedPlatforms.value = platforms.filter(p => 
        defaultPlatforms.includes(p.toUpperCase())
      )
      
      // 设置日期范围为最近30天
      setRecentDays(30)
      
      // 智能默认选中：仅选择 Top 10 交易量最大的 Token
      selectTopN(10)
      
      unwatch?.()
    }
  }, { immediate: true })
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
          <span class="stat-label">已选代币</span>
          <span class="stat-value highlight">{{ selectedTokens.length }} / {{ availableTokens.length }}</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item" v-if="isPerformanceMode">
          <span class="stat-label">⚡ 性能模式</span>
          <span class="stat-value highlight">已启用</span>
        </div>
      </div>

      <!-- 中间：图表模式切换 -->
      <div class="toolbar-mode-switch">
        <div class="mode-switch-group">
          <button 
            class="mode-btn" 
            :class="{ active: chartMode === 'volume' }"
            @click="chartMode = 'volume'"
            title="显示24小时交易量"
          >
            交易量
          </button>
          <button 
            class="mode-btn" 
            :class="{ active: chartMode === 'change' }"
            @click="chartMode = 'change'"
            title="显示24小时交易量变化率"
          >
            变化率 %
          </button>
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
        <button 
          class="toggle-sidebar-btn"
          @click="showTokenSelector = !showTokenSelector"
          :title="showTokenSelector ? '隐藏选择器' : '显示选择器'"
        >
          {{ showTokenSelector ? '◀' : '▶' }}
        </button>
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
            max="20"
            step="0.5"
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

    <!-- 主内容区域 -->
    <div class="chart-main">
      <!-- 图表区域 -->
      <div class="chart-content">
        <v-chart 
          class="chart" 
          :option="chartOption" 
          autoresize
        />
      </div>

      <!-- Token 选择器侧边栏 -->
      <div class="token-sidebar" v-show="showTokenSelector">
        <div class="sidebar-header">
          <h3>Token 列表</h3>
          <div class="quick-actions">
            <button @click="selectTopN(10)" class="action-btn" title="选择 Top 10">Top 10</button>
            <button @click="selectTopN(20)" class="action-btn" title="选择 Top 20">Top 20</button>
            <button @click="selectAllTokens" class="action-btn" title="全选">全选</button>
            <button @click="clearSelection" class="action-btn clear" title="清空">清空</button>
          </div>
        </div>
        
        <div class="sidebar-controls">
          <input 
            type="text"
            v-model="searchQuery"
            placeholder="搜索 Token..."
            class="search-input"
          >
          <select v-model="sortBy" class="sort-select">
            <option value="hotness">按热度 (推荐)</option>
            <option value="volume">按交易量</option>
            <option value="name">按名称</option>
            <option value="change">按涨跌幅</option>
          </select>
        </div>

        <div class="token-list">
          <div 
            v-for="token in filteredTokensWithInfo" 
            :key="token.symbol"
            class="token-item"
            :class="{ selected: selectedTokens.includes(token.symbol) }"
            @click="toggleToken(token.symbol)"
          >
            <div class="token-main">
              <span class="token-checkbox">
                {{ selectedTokens.includes(token.symbol) ? '☑' : '☐' }}
              </span>
              <span class="token-symbol">{{ token.symbol }}</span>
            </div>
            <div class="token-info">
              <span class="token-volume">{{ formatVolume(token.latestVolume) }}</span>
              <span 
                class="token-change"
                :class="{ positive: token.volumeChange > 0, negative: token.volumeChange < 0 }"
              >
                {{ formatChange(token.volumeChange) }}
              </span>
            </div>
          </div>
          <div v-if="filteredTokensWithInfo.length === 0" class="no-tokens">
            未找到匹配的 Token
          </div>
        </div>
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

/* 模式切换按钮 */
.toolbar-mode-switch {
  display: flex;
  align-items: center;
  justify-content: center;
}

.mode-switch-group {
  display: flex;
  background-color: rgba(0, 0, 0, 0.2);
  border-radius: 20px;
  padding: 3px;
}

.mode-btn {
  padding: 5px 15px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.2s;
}

.mode-btn:hover {
  color: white;
}

.mode-btn.active {
  background-color: white;
  color: #667eea;
  font-weight: 600;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
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

.toggle-sidebar-btn {
  padding: 6px 10px;
  background-color: rgba(255, 255, 255, 0.15);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.toggle-sidebar-btn:hover {
  background-color: rgba(255, 255, 255, 0.25);
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
  border: 1px solid var(--border-color);
  color: var(--text-color);
  border-radius: 4px;
  cursor: pointer;
  font-size: 10px;
  opacity: 0.7;
}

.toggle-all-btn:hover {
  opacity: 1;
  background-color: var(--hover-color);
}

.volume-control {
  display: flex;
  align-items: center;
  gap: 10px;
}

.volume-slider {
  width: 120px;
  accent-color: #667eea;
}

.volume-value {
  font-size: 12px;
  font-weight: 600;
  color: #667eea;
  min-width: 50px;
}

.filter-divider {
  width: 1px;
  height: 40px;
  background-color: var(--border-color);
  margin: 0 5px;
}

.platform-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.platform-tag {
  padding: 3px 10px;
  background-color: var(--bg-color);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
  color: var(--text-color);
}

.platform-tag:hover {
  border-color: #667eea;
  color: #667eea;
}

.platform-tag.selected {
  background-color: #667eea;
  color: white;
  border-color: #667eea;
}

/* 主内容区域 */
.chart-main {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}

.chart-content {
  flex: 1;
  height: 100%;
  position: relative;
  overflow: hidden;
}

.chart {
  width: 100%;
  height: 100%;
}

/* 侧边栏 */
.token-sidebar {
  width: 260px;
  background-color: var(--sidebar-bg);
  border-left: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.3s;
}

.sidebar-header {
  padding: 15px;
  border-bottom: 1px solid var(--border-color);
}

.sidebar-header h3 {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: var(--text-color);
}

.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.action-btn {
  padding: 4px 8px;
  font-size: 11px;
  border: 1px solid var(--border-color);
  background-color: var(--bg-color);
  color: var(--text-color);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  border-color: #667eea;
  color: #667eea;
}

.action-btn.clear {
  color: #f44336;
  border-color: rgba(244, 67, 54, 0.3);
}

.action-btn.clear:hover {
  background-color: #ffebee;
  border-color: #f44336;
}

.sidebar-controls {
  padding: 10px 15px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.search-input {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background-color: var(--bg-color);
  color: var(--text-color);
  font-size: 12px;
}

.search-input:focus {
  border-color: #667eea;
  outline: none;
}

.sort-select {
  width: 100%;
  padding: 6px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background-color: var(--bg-color);
  color: var(--text-color);
  font-size: 12px;
}

.token-list {
  flex: 1;
  overflow-y: auto;
  padding: 5px 0;
}

.token-item {
  padding: 8px 15px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-color);
  transition: background-color 0.2s;
}

.token-item:hover {
  background-color: var(--hover-color);
}

.token-item.selected {
  background-color: rgba(102, 126, 234, 0.1);
  border-left: 3px solid #667eea;
}

.token-main {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.token-checkbox {
  color: #667eea;
  font-size: 14px;
}

.token-symbol {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-color);
}

.token-info {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #888;
  padding-left: 22px;
}

.token-change.positive {
  color: #4caf50;
}

.token-change.negative {
  color: #f44336;
}

.no-tokens {
  padding: 20px;
  text-align: center;
  color: #999;
  font-size: 12px;
}

/* 滚动条样式 */
.token-list::-webkit-scrollbar {
  width: 6px;
}

.token-list::-webkit-scrollbar-track {
  background: transparent;
}

.token-list::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.1);
  border-radius: 3px;
}

.token-list::-webkit-scrollbar-thumb:hover {
  background-color: rgba(0, 0, 0, 0.2);
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
  
  .token-sidebar {
    width: 220px;
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
  
  .chart-main {
    flex-direction: column;
  }
  
  .token-sidebar {
    width: 100%;
    max-height: 200px;
    border-left: none;
    border-top: 1px solid var(--border-color);
  }
}
</style>
