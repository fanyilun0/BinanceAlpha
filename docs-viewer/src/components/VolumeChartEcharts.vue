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
  ToolboxComponent,
  MarkLineComponent
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
  ToolboxComponent,
  MarkLineComponent
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
const sortBy = ref('auto') // 排序方式: auto (根据图表模式自动), hotness, volume, name, change
const showTokenSelector = ref(true) // 是否显示 Token 选择器
const chartMode = ref('volume') // 图表模式: 'volume' (交易量), 'change' (变化率)
const showAggregatedLine = ref(true) // 是否显示"其他代币"聚合线
const focusCount = ref(10) // 焦点组显示的 Token 数量
const highlightedToken = ref(null) // 当前高亮的 Token
const tokenRangeStart = ref(1) // Token 范围起始
const tokenRangeEnd = ref(50) // Token 范围结束

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

// 实际使用的排序方式（auto 模式根据图表模式自动选择）
const effectiveSortBy = computed(() => {
  if (sortBy.value === 'auto') {
    // 交易量图表按交易量排序，变化率图表按变化率排序
    return chartMode.value === 'volume' ? 'volume' : 'change'
  }
  return sortBy.value
})

// 排序后的 Token 列表
const sortedTokens = computed(() => {
  const tokens = [...baseFilteredTokens.value]
  
  if (effectiveSortBy.value === 'volume') {
    tokens.sort((a, b) => b.latestVolume - a.latestVolume)
  } else if (effectiveSortBy.value === 'name') {
    tokens.sort((a, b) => a.symbol.localeCompare(b.symbol))
  } else if (effectiveSortBy.value === 'change') {
    tokens.sort((a, b) => b.volumeChange - a.volumeChange)
  } else if (effectiveSortBy.value === 'hotness') {
    tokens.sort((a, b) => b.hotness - a.hotness)
  }
  
  return tokens
})

// 应用 range 范围筛选后的 Token 列表
const rangeFilteredTokens = computed(() => {
  const start = Math.max(0, tokenRangeStart.value - 1)
  const end = Math.min(sortedTokens.value.length, tokenRangeEnd.value)
  return sortedTokens.value.slice(start, end)
})

// 最终显示的 Token 列表 (应用搜索和 range 筛选)
const filteredTokensWithInfo = computed(() => {
  let tokens = rangeFilteredTokens.value
  if (debouncedSearchQuery.value) {
    const query = debouncedSearchQuery.value.toLowerCase()
    tokens = tokens.filter(t => t.symbol.toLowerCase().includes(query))
  }
  return tokens
})

// 可用的 token 符号列表（应用 range 筛选）
const availableTokens = computed(() => {
  return rangeFilteredTokens.value.map(t => t.symbol)
})

// 总 Token 数量（未筛选）
const totalTokenCount = computed(() => {
  return sortedTokens.value.length
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

// 数据对齐与标准化函数 - 处理缺失数据
const alignDataToTimeline = (volumes, mode = 'volume') => {
  if (!volumes) return []
  
  return volumes.map(v => {
    if (v === null || v === undefined) {
      // 交易量模式：缺失填充为 0（表示无交易）
      // 变化率模式：保持 null（表示未知）
      return mode === 'volume' ? 0 : null
    }
    return v
  })
}

// 计算日环比变化率数据
const calculateDailyChange = (volumes) => {
  if (!volumes || volumes.length < 2) return volumes.map(() => null)
  
  const changes = []
  // 第一个点没有前一天，设为 null
  changes.push(null)
  
  for (let i = 1; i < volumes.length; i++) {
    const curr = volumes[i]
    const prev = volumes[i-1]
    
    if (prev !== null && prev !== undefined && prev > 0 && curr !== null && curr !== undefined) {
      const change = ((curr - prev) / prev) * 100
      changes.push(change)
    } else {
      // 数据缺失时保持 null，不强制填充 0
      changes.push(null)
    }
  }
  return changes
}

// 计算聚合线数据（市场平均）
const calculateAggregatedLine = (tokensData, excludeSymbols, start, end, isChangeMode) => {
  if (!tokensData || tokensData.length === 0) return []
  
  // 过滤掉焦点组的 Token
  const otherTokens = tokensData.filter(t => !excludeSymbols.includes(t.symbol))
  if (otherTokens.length === 0) return []
  
  const dateCount = end - start + 1
  const aggregated = []
  
  for (let i = 0; i < dateCount; i++) {
    const dayIndex = start + i
    let validValues = []
    
    otherTokens.forEach(token => {
      let value
      if (isChangeMode) {
        const changes = calculateDailyChange(token.volumes)
        value = changes[dayIndex]
      } else {
        value = token.volumes[dayIndex]
      }
      
      if (value !== null && value !== undefined && !isNaN(value)) {
        validValues.push(value)
      }
    })
    
    if (validValues.length > 0) {
      // 使用中位数而非平均值，更能抵抗极端值
      validValues.sort((a, b) => a - b)
      const mid = Math.floor(validValues.length / 2)
      const median = validValues.length % 2 !== 0 
        ? validValues[mid] 
        : (validValues[mid - 1] + validValues[mid]) / 2
      aggregated.push(median)
    } else {
      aggregated.push(null)
    }
  }
  
  return aggregated
}

// 检查 Token 数据稀疏度（有效数据占比）
const getDataDensity = (volumes) => {
  if (!volumes || volumes.length === 0) return 0
  const validCount = volumes.filter(v => v !== null && v !== undefined && v > 0).length
  return validCount / volumes.length
}

// 获取焦点组 Token（显示独立线条的）
const focusGroupTokens = computed(() => {
  return selectedTokens.value.slice(0, focusCount.value)
})

// 获取聚合组 Token（合并为"其他"线的）
const aggregatedGroupTokens = computed(() => {
  return selectedTokens.value.slice(focusCount.value)
})

// 聚合组的 Token 数量
const aggregatedCount = computed(() => {
  return aggregatedGroupTokens.value.length
})

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

  // 构建焦点组的 series
  const series = focusGroupTokens.value.map((token, index) => {
    const tokenInfo = tokenInfoCache.value.find(t => t.symbol === token)
    if (!tokenInfo) return null
    
    let displayData
    if (isChangeMode) {
      const fullChangeData = calculateDailyChange(tokenInfo.volumes)
      displayData = fullChangeData.slice(start, end + 1)
    } else {
      // 对交易量数据进行对齐处理：null -> 0
      const alignedVolumes = alignDataToTimeline(tokenInfo.volumes, 'volume')
      displayData = alignedVolumes.slice(start, end + 1)
    }
    
    const color = generateColor(index)
    const isHighlighted = highlightedToken.value === token
    const isDimmed = highlightedToken.value && highlightedToken.value !== token
    
    return {
      name: token,
      type: 'line',
      data: displayData,
      smooth: true,
      symbol: isPerformanceMode.value ? 'none' : 'circle',
      symbolSize: isHighlighted ? 6 : (isPerformanceMode.value ? 0 : 4),
      sampling: isPerformanceMode.value ? 'lttb' : undefined,
      z: isHighlighted ? 100 : 10, // 高亮时提升层级
      lineStyle: {
        width: isHighlighted ? 3 : (isPerformanceMode.value ? 1.5 : 2),
        color: color,
        opacity: isDimmed ? 0.15 : 1 // 悬停高亮时降低其他线条透明度
      },
      itemStyle: {
        color: color,
        opacity: isDimmed ? 0.15 : 1
      },
      emphasis: {
        focus: 'series',
        blurScope: 'coordinateSystem'
      },
      // 变化率模式下不连接空数据，交易量模式连接
      connectNulls: !isChangeMode
    }
  }).filter(Boolean)

  // 添加聚合组的"其他代币"线
  if (showAggregatedLine.value && aggregatedCount.value > 0) {
    const aggregatedData = calculateAggregatedLine(
      tokenInfoCache.value.filter(t => aggregatedGroupTokens.value.includes(t.symbol)),
      [], // 不排除任何 token，因为已经筛选过了
      start,
      end,
      isChangeMode
    )
    
    const isDimmed = highlightedToken.value && highlightedToken.value !== '📊 其他代币'
    
    series.push({
      name: `📊 其他代币 (${aggregatedCount.value}个)`,
      type: 'line',
      data: aggregatedData,
      smooth: true,
      symbol: 'none',
      lineStyle: {
        width: 2.5,
        color: '#999',
        type: 'dashed',
        opacity: isDimmed ? 0.15 : 0.8
      },
      itemStyle: {
        color: '#999',
        opacity: isDimmed ? 0.15 : 0.8
      },
      emphasis: {
        focus: 'series',
        blurScope: 'coordinateSystem'
      },
      connectNulls: true,
      z: 5 // 放在底层
    })
  }

  // 智能 Y 轴配置：处理极端值
  let yAxisConfig = {
    type: isChangeMode ? 'value' : 'log',
    logBase: 10,
    position: 'left',
    name: isChangeMode ? '24H 变化率 (%)' : '24H 交易量 (USD)',
    nameLocation: 'end',
    nameTextStyle: {
      align: 'right',
      padding: [0, 10, 0, 0]
    },
    axisLabel: {
      formatter: isChangeMode ? '{value}%' : function(value) {
        if (value >= 1000) return '$' + (value / 1000).toFixed(1) + 'B'
        return '$' + value + 'M'
      },
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
  }

  // 变化率模式：限制 Y 轴范围防止极端值压缩视图
  if (isChangeMode) {
    yAxisConfig.max = 500  // 限制最大值为 500%
    yAxisConfig.min = -100 // 限制最小值为 -100%
  } else {
    // 交易量模式：设置合理的范围，使用对数轴自动适应
    yAxisConfig.min = 1 // 最小 10K
    yAxisConfig.max = 10000 // 最小 10K
    // 不设置 max，让 ECharts 自动计算
  }

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        label: {
          backgroundColor: '#6a7985'
        }
      },
      backgroundColor: 'rgba(0, 0, 0, 0.9)',
      borderColor: '#667eea',
      borderWidth: 1,
      textStyle: {
        color: '#fff',
        fontSize: 12
      },
      extraCssText: 'max-height: 400px; overflow-y: auto;',
      // 优化 Tooltip：排序、分组、限制显示
      formatter: function(params) {
        if (!params || params.length === 0) return ''
        
        // 分离焦点组和聚合组
        const focusParams = []
        let aggregatedParam = null
        
        params.forEach(param => {
          if (param.seriesName.startsWith('📊')) {
            aggregatedParam = param
          } else {
            focusParams.push(param)
          }
        })
        
        // 按数值降序排序焦点组
        focusParams.sort((a, b) => {
          const valA = a.value !== null && a.value !== undefined ? Math.abs(a.value) : -Infinity
          const valB = b.value !== null && b.value !== undefined ? Math.abs(b.value) : -Infinity
          return valB - valA
        })
        
        // 限制显示数量
        const maxDisplay = 10
        const displayParams = focusParams.slice(0, maxDisplay)
        const remaining = focusParams.length - maxDisplay
        
        let result = `<div style="font-weight: bold; margin-bottom: 8px; font-size: 13px; border-bottom: 1px solid #667eea; padding-bottom: 5px; color: #fff;">${params[0].axisValue}</div>`
        
        // 显示焦点组数据
        displayParams.forEach(param => {
          let valueStr = ''
          let colorStyle = ''
          let statusIcon = ''
          
          if (param.value === null || param.value === undefined) {
            valueStr = '无数据'
            colorStyle = 'color: #666;'
            statusIcon = '⚠️ '
          } else if (isChangeMode) {
            const val = param.value
            // 标记被截断的极端值
            if (val > 200) {
              valueStr = `+${val.toFixed(1)}% 🔥`
              colorStyle = 'color: #ff6b6b;'
            } else if (val < -100) {
              valueStr = `${val.toFixed(1)}% ❄️`
              colorStyle = 'color: #4ecdc4;'
            } else {
              const sign = val > 0 ? '+' : ''
              valueStr = `${sign}${val.toFixed(2)}%`
              if (val > 0) colorStyle = 'color: #ff6b6b;'
              else if (val < 0) colorStyle = 'color: #4ecdc4;'
            }
          } else {
            if (param.value === 0) {
              valueStr = '$0 (无交易)'
              colorStyle = 'color: #888;'
            } else {
              valueStr = `$${param.value.toFixed(2)}M`
            }
          }
          
          result += `<div style="margin: 4px 0; display: flex; align-items: center; gap: 8px;">
            <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background-color:${param.color};flex-shrink:0;"></span>
            <span style="flex: 1; max-width: 90px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${statusIcon}${param.seriesName}</span>
            <span style="font-weight: bold; ${colorStyle} text-align: right; min-width: 80px;">${valueStr}</span>
          </div>`
        })
        
        if (remaining > 0) {
          result += `<div style="margin: 5px 0; color: #888; font-size: 11px; text-align: center; border-top: 1px dashed #444; padding-top: 5px;">...还有 ${remaining} 个焦点 Token</div>`
        }
        
        // 显示聚合组数据
        if (aggregatedParam && aggregatedParam.value !== null) {
          result += `<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #555;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="display:inline-block;width:10px;height:2px;background-color:#999;flex-shrink:0;"></span>
              <span style="flex: 1; color: #aaa;">${aggregatedParam.seriesName}</span>
              <span style="font-weight: bold; color: #aaa;">${isChangeMode ? aggregatedParam.value.toFixed(2) + '%' : '$' + aggregatedParam.value.toFixed(2) + 'M'}</span>
            </div>
            <div style="font-size: 10px; color: #666; margin-top: 2px; padding-left: 18px;">中位数</div>
          </div>`
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
      },
      // 点击图例时触发高亮
      selected: {}
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
        fillerColor: 'rgba(102, 126, 234, 0.2)',
        handleStyle: {
          color: '#667eea'
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
    yAxis: yAxisConfig,
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
          <span class="stat-label">焦点/聚合</span>
          <span class="stat-value highlight">{{ focusGroupTokens.length }} + {{ aggregatedCount }}</span>
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

      <!-- 焦点组数量控制 -->
      <div class="filter-item">
        <span class="filter-label">焦点显示</span>
        <div class="focus-control">
          <input 
            type="range" 
            v-model.number="focusCount"
            min="3"
            max="30"
            step="1"
            class="focus-slider"
          >
          <span class="focus-value">Top {{ focusCount }}</span>
        </div>
      </div>

      <div class="filter-divider"></div>

      <!-- 聚合线开关 -->
      <div class="filter-item">
        <label class="toggle-switch">
          <input type="checkbox" v-model="showAggregatedLine">
          <span class="toggle-slider"></span>
        </label>
        <span class="filter-label" style="margin-left: 8px;">显示聚合线</span>
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
            <option value="auto">自动排序 (推荐)</option>
            <option value="volume">按交易量</option>
            <option value="change">按涨跌幅</option>
            <option value="hotness">按热度</option>
            <option value="name">按名称</option>
          </select>
          
          <!-- Range 选择器 -->
          <div class="range-selector">
            <div class="range-label">
              <span>排名范围</span>
              <span class="range-value">{{ tokenRangeStart }} - {{ tokenRangeEnd }} / {{ totalTokenCount }}</span>
            </div>
            <div class="range-sliders">
              <div class="range-slider-group">
                <label>起始:</label>
                <input 
                  type="range" 
                  v-model.number="tokenRangeStart"
                  :min="1"
                  :max="Math.min(tokenRangeEnd, totalTokenCount)"
                  class="range-slider"
                >
                <span class="range-num">{{ tokenRangeStart }}</span>
              </div>
              <div class="range-slider-group">
                <label>结束:</label>
                <input 
                  type="range" 
                  v-model.number="tokenRangeEnd"
                  :min="tokenRangeStart"
                  :max="Math.min(199, totalTokenCount)"
                  class="range-slider"
                >
                <span class="range-num">{{ tokenRangeEnd }}</span>
              </div>
            </div>
            <div class="range-presets">
              <button @click="tokenRangeStart = 1; tokenRangeEnd = 20" class="range-preset-btn">1-20</button>
              <button @click="tokenRangeStart = 1; tokenRangeEnd = 50" class="range-preset-btn">1-50</button>
              <button @click="tokenRangeStart = 1; tokenRangeEnd = 100" class="range-preset-btn">1-100</button>
              <button @click="tokenRangeStart = 50; tokenRangeEnd = 100" class="range-preset-btn">50-100</button>
              <button @click="tokenRangeStart = 100; tokenRangeEnd = Math.min(199, totalTokenCount)" class="range-preset-btn">100+</button>
            </div>
          </div>
        </div>

        <div class="token-list">
          <div 
            v-for="(token, index) in filteredTokensWithInfo" 
            :key="token.symbol"
            class="token-item"
            :class="{ 
              selected: selectedTokens.includes(token.symbol),
              'in-focus': focusGroupTokens.includes(token.symbol),
              'in-aggregated': aggregatedGroupTokens.includes(token.symbol),
              highlighted: highlightedToken === token.symbol
            }"
            @click="toggleToken(token.symbol)"
            @mouseenter="highlightedToken = token.symbol"
            @mouseleave="highlightedToken = null"
          >
            <div class="token-main">
              <span class="token-checkbox">
                {{ selectedTokens.includes(token.symbol) ? '☑' : '☐' }}
              </span>
              <span class="token-symbol">{{ token.symbol }}</span>
              <span 
                v-if="focusGroupTokens.includes(token.symbol)" 
                class="token-badge focus"
                :title="`焦点组 #${selectedTokens.indexOf(token.symbol) + 1}`"
              >
                #{{ selectedTokens.indexOf(token.symbol) + 1 }}
              </span>
              <span 
                v-else-if="aggregatedGroupTokens.includes(token.symbol)" 
                class="token-badge aggregated"
                title="已聚合到'其他代币'线"
              >
                聚合
              </span>
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

/* 焦点组数量控制 */
.focus-control {
  display: flex;
  align-items: center;
  gap: 10px;
}

.focus-slider {
  width: 100px;
  accent-color: #667eea;
}

.focus-value {
  font-size: 12px;
  font-weight: 600;
  color: #667eea;
  min-width: 55px;
}

/* 开关样式 */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: 0.3s;
  border-radius: 20px;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 14px;
  width: 14px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
}

.toggle-switch input:checked + .toggle-slider {
  background-color: #667eea;
}

.toggle-switch input:checked + .toggle-slider:before {
  transform: translateX(16px);
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
  transition: all 0.2s;
}

.token-item:hover {
  background-color: var(--hover-color);
}

.token-item.selected {
  background-color: rgba(102, 126, 234, 0.08);
  border-left: 3px solid #667eea;
}

/* 焦点组样式 */
.token-item.in-focus {
  background-color: rgba(102, 126, 234, 0.12);
  border-left: 3px solid #667eea;
}

/* 聚合组样式 */
.token-item.in-aggregated {
  background-color: rgba(153, 153, 153, 0.08);
  border-left: 3px solid #999;
}

/* 高亮状态 */
.token-item.highlighted {
  background-color: rgba(102, 126, 234, 0.2);
  box-shadow: inset 0 0 0 2px #667eea;
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
  flex: 1;
}

/* Token 徽章 */
.token-badge {
  font-size: 9px;
  padding: 2px 5px;
  border-radius: 8px;
  font-weight: 600;
  flex-shrink: 0;
}

.token-badge.focus {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.token-badge.aggregated {
  background-color: #e0e0e0;
  color: #666;
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
