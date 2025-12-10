<script setup>
import { ref, computed, onMounted } from 'vue'

const props = defineProps({
  tableData: {
    type: [Object, Array],
    required: true
  }
})

const sortColumn = ref('')
const sortDirection = ref('asc') // 'asc' or 'desc'
const futuresSymbols = ref([])

// 加载合约交易对列表
onMounted(async () => {
  try {
    const response = await fetch('/futures_symbols.json')
    futuresSymbols.value = await response.json()
  } catch (error) {
    console.error('Error loading futures symbols:', error)
    futuresSymbols.value = []
  }
})

// 检查是否有合约交易对
const checkFuturesListing = (symbol) => {
  if (!symbol || !futuresSymbols.value.length) return false
  
  // 标准化symbol格式（去除特殊字符，转大写）
  const normalizedSymbol = symbol.toUpperCase().replace(/[^A-Z0-9]/g, '')
  
  // 检查是否存在对应的USDT或USDC合约
  const usdtPair = `${normalizedSymbol}USDT`
  const usdcPair = `${normalizedSymbol}USDC`
  
  return futuresSymbols.value.includes(usdtPair) || futuresSymbols.value.includes(usdcPair)
}

// 判断是否为原始数组数据（filtered_crypto_list 格式）
const isRawData = computed(() => {
  return Array.isArray(props.tableData)
})

// 判断是否为趋势信号数据（trend_signals 格式）
const isTrendSignalData = computed(() => {
  if (!props.tableData || Array.isArray(props.tableData)) return false
  return props.tableData.title?.includes('吸筹') || 
         props.tableData.title?.includes('洗盘') ||
         props.tableData.columns?.includes('信号类型')
})

// 转换原始数据为表格格式
const formattedTableData = computed(() => {
  if (isRawData.value) {
    // 原始数据格式，需要转换
    const data = props.tableData.map(item => {
      const usdQuote = item.quotes?.find(q => q.name === 'USD')
      const marketCap = usdQuote?.marketCap || 0
      const volume24h = usdQuote?.volume24h || 0
      const totalSupply = item.totalSupply || 0
      const circulatingSupply = item.circulatingSupply || 0
      const price = usdQuote?.price || 0
      const symbol = item.symbol || ''
      
      // 计算FDV (Fully Diluted Valuation) = 价格 × 总供应量
      const fdv = totalSupply > 0 && price > 0 ? price * totalSupply : 0
      
      // 计算Vol/MC比率
      const volMcRatio = marketCap > 0 && volume24h > 0 ? (volume24h / marketCap) : 0
      
      // 计算MC/FDV比率
      const mcFdvRatio = fdv > 0 && marketCap > 0 ? (marketCap / fdv) : 0
      
      // 检查是否有合约
      const hasFutures = checkFuturesListing(symbol)
      
      return {
        '排名': item.cmcRank || '-',
        '名称': item.name || '-',
        '代号': symbol || '-',
        '合约': hasFutures ? '是' : '否',
        '价格(USD)': price > 0 ? `$${price.toFixed(6)}` : '-',
        '24h变化(%)': usdQuote?.percentChange24h ? usdQuote.percentChange24h.toFixed(2) : '-',
        '7d变化(%)': usdQuote?.percentChange7d ? usdQuote.percentChange7d.toFixed(2) : '-',
        '市值(MC)': marketCap > 0 ? `$${(marketCap / 1000000).toFixed(2)}M` : '-',
        '24h交易量': volume24h > 0 ? `$${(volume24h / 1000000).toFixed(2)}M` : '-',
        'Vol/MC': volMcRatio > 0 ? volMcRatio.toFixed(2) : '-',
        'FDV': fdv > 0 ? `$${(fdv / 1000000).toFixed(2)}M` : '-',
        'MC/FDV': mcFdvRatio > 0 ? mcFdvRatio.toFixed(2) : '-',
        '流通量': circulatingSupply > 0 ? circulatingSupply.toLocaleString() : '-',
        '总供应量': totalSupply > 0 ? totalSupply.toLocaleString() : '-',
        '平台': item.platform?.symbol || '-',
      }
    })
    
    return {
      title: '加密货币列表',
      date: new Date().toLocaleDateString('zh-CN'),
      total_count: data.length,
      columns: ['排名', '名称', '代号', '平台', '价格(USD)',  '合约','24h变化(%)', '7d变化(%)', '市值(MC)', '24h交易量', 'Vol/MC', 'FDV', 'MC/FDV'],
      data: data
    }
  } else if (isTrendSignalData.value) {
    // 吸筹/洗盘信号数据格式
    return {
      title: props.tableData.title || '吸筹/洗盘信号分析',
      date: props.tableData.date || new Date().toLocaleDateString('zh-CN'),
      total_count: props.tableData.total_count || props.tableData.data?.length || 0,
      summary: props.tableData.summary || null,
      // 精简列展示，隐藏 raw 字段
      columns: ['代号', '名称', '信号类型', '置信度', '交易量变化(%)', '价格变化(%)', '24h交易量', '市值', '平台', 'T0换手率', 'T-1换手率', 'T-2换手率', '信号解读'],
      data: props.tableData.data || []
    }
  } else {
    // 已格式化的表格数据
    return props.tableData
  }
})

// 格式化单元格数据
const formatCellValue = (value, column) => {
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  
  // 数字类型的列
  if (typeof value === 'number') {
    return value.toLocaleString()
  }
  
  return value
}

// 获取单元格颜色（与图片样式保持一致）
const getCellColor = (row, column) => {
  // 24h变化(%) 和 7d变化(%) 列 - 减少梯度，与图片保持一致
  if (column === '24h变化(%)' || column === '7d变化(%)') {
    const value = parseFloat(row[column])
    if (isNaN(value)) return 'transparent'
    if (value >= 50) return '#00b050'  // 暴涨：深绿色
    if (value >= 20) return '#92d050'  // 大涨：中绿色
    if (value > 0) return '#d8f3dc'    // 小涨：浅绿色
    if (value <= -50) return '#c00000' // 暴跌：深红色
    if (value <= -20) return '#ff6b6b' // 大跌：中红色
    if (value < 0) return '#ffccd5'    // 小跌：浅红色
  }
  
  // 合约列 - 有合约的显示浅蓝色
  if (column === '合约') {
    const value = row[column]
    if (value === '是') {
      return '#e0f7fa'  // 浅蓝色
    }
  }
  
  // 信号类型列 - 不同类型不同颜色
  if (column === '信号类型') {
    const value = row[column]
    if (value?.includes('稳定吸筹') || value?.includes('持续吸筹')) {
      return '#e8d5f5'  // 紫色 - 稳定吸筹
    }
    if (value?.includes('疑似吸筹')) {
      return '#f3e5f5'  // 浅紫色 - 疑似吸筹
    }
    if (value?.includes('洗盘结束')) {
      return '#fff8e1'  // 黄色 - 洗盘结束
    }
    if (value?.includes('牛旗')) {
      return '#e8f5e9'  // 绿色 - 牛旗整理
    }
    if (value?.includes('出货') || value?.includes('洗盘')) {
      return '#ffebee'  // 红色 - 出货/洗盘
    }
  }
  
  // 置信度列 - 高置信度高亮
  if (column === '置信度') {
    const value = parseFloat(row[column])
    if (isNaN(value)) return 'transparent'
    if (value >= 0.85) return '#c8e6c9'  // 高置信度：绿色
    if (value >= 0.7) return '#fff9c4'   // 中置信度：黄色
    return 'transparent'
  }
  
  // 交易量变化(%) 列
  if (column === '交易量变化(%)') {
    const value = parseFloat(row[column])
    if (isNaN(value)) return 'transparent'
    if (value >= 100) return '#00b050'  // 暴涨：深绿色
    if (value >= 50) return '#92d050'   // 大涨：中绿色
    if (value > 0) return '#d8f3dc'     // 小涨：浅绿色
    if (value <= -50) return '#c00000'  // 暴跌：深红色
    if (value < 0) return '#ffccd5'     // 小跌：浅红色
  }
  
  // 价格变化(%) 列
  if (column === '价格变化(%)') {
    const value = parseFloat(row[column])
    if (isNaN(value)) return 'transparent'
    if (value >= 10) return '#92d050'   // 大涨
    if (value > 0) return '#d8f3dc'     // 小涨
    if (value <= -10) return '#ff6b6b'  // 大跌
    if (value < 0) return '#ffccd5'     // 小跌
  }
  
  return 'transparent'
}

// 获取单元格文本颜色
const getCellTextColor = (row, column) => {
  if (column === '24h变化(%)' || column === '7d变化(%)') {
    const value = parseFloat(row[column])
    if (isNaN(value)) return 'inherit'
    // 对于深色背景使用白色文字
    if (value >= 50 || value <= -50 || (value >= 20 && value < 50) || (value <= -20 && value > -50)) {
      return 'white'
    }
  }
  
  // 交易量变化列
  if (column === '交易量变化(%)') {
    const value = parseFloat(row[column])
    if (isNaN(value)) return 'inherit'
    if (value >= 100 || value <= -50) return 'white'
  }
  
  return 'inherit'
}

// 排序处理
const handleSort = (column) => {
  if (sortColumn.value === column) {
    // 切换排序方向
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortColumn.value = column
    sortDirection.value = 'asc'
  }
}

// 排序后的数据
const sortedData = computed(() => {
  if (!sortColumn.value) {
    return formattedTableData.value.data
  }
  
  const data = [...formattedTableData.value.data]
  const column = sortColumn.value
  
  data.sort((a, b) => {
    let aVal = a[column]
    let bVal = b[column]
    
    // 处理特殊值
    if (aVal === '是') aVal = 1
    if (aVal === '否') aVal = 0
    if (bVal === '是') bVal = 1
    if (bVal === '否') bVal = 0
    
    // 处理百分比和数字字符串
    if (typeof aVal === 'string' && aVal.includes('%')) {
      aVal = parseFloat(aVal)
    }
    if (typeof bVal === 'string' && bVal.includes('%')) {
      bVal = parseFloat(bVal)
    }
    
    // 处理货币字符串（如 $1.23M）
    if (typeof aVal === 'string' && aVal.startsWith('$')) {
      const match = aVal.match(/\$([\d.]+)([KMB]?)/)
      if (match) {
        const multiplier = { K: 1000, M: 1000000, B: 1000000000 }
        aVal = parseFloat(match[1]) * (multiplier[match[2]] || 1)
      }
    }
    if (typeof bVal === 'string' && bVal.startsWith('$')) {
      const match = bVal.match(/\$([\d.]+)([KMB]?)/)
      if (match) {
        const multiplier = { K: 1000, M: 1000000, B: 1000000000 }
        bVal = parseFloat(match[1]) * (multiplier[match[2]] || 1)
      }
    }
    
    // 数字排序
    if (typeof aVal === 'number' && typeof bVal === 'number') {
      return sortDirection.value === 'asc' ? aVal - bVal : bVal - aVal
    }
    
    // 字符串排序
    const aStr = String(aVal || '')
    const bStr = String(bVal || '')
    
    if (sortDirection.value === 'asc') {
      return aStr.localeCompare(bStr, 'zh-CN', { numeric: true })
    } else {
      return bStr.localeCompare(aStr, 'zh-CN', { numeric: true })
    }
  })
  
  return data
})

// 获取排序图标
const getSortIcon = (column) => {
  if (sortColumn.value !== column) return '↕️'
  return sortDirection.value === 'asc' ? '↑' : '↓'
}
</script>

<template>
  <div class="table-viewer">
    <div class="table-header">
      <h2>{{ formattedTableData.title }}</h2>
      <div class="table-info">
        <span>日期: {{ formattedTableData.date }}</span>
        <span>数据量: {{ formattedTableData.total_count }} 条</span>
      </div>
      <!-- 趋势信号 Summary -->
      <div v-if="formattedTableData.summary" class="table-summary">
        <span class="summary-item summary-trend">
          📊 趋势信号: {{ formattedTableData.summary.trend_signals_count || 0 }}
        </span>
        <span class="summary-item summary-accumulation">
          🐋 吸筹: {{ formattedTableData.summary.accumulation_count || 0 }}
        </span>
        <span class="summary-item summary-distribution">
          ⚠️ 出货/洗盘: {{ formattedTableData.summary.distribution_count || 0 }}
        </span>
      </div>
    </div>
    
    <div class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th 
              v-for="column in formattedTableData.columns" 
              :key="column"
              @click="handleSort(column)"
              class="sortable"
            >
              {{ column }}
              <span class="sort-icon">{{ getSortIcon(column) }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in sortedData" :key="index">
            <td 
              v-for="column in formattedTableData.columns" 
              :key="column"
              :style="{
                backgroundColor: getCellColor(row, column),
                color: getCellTextColor(row, column)
              }"
            >
              {{ formatCellValue(row[column], column) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.table-viewer {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.table-header {
  padding: 20px 20px 15px 20px;
  border-bottom: 2px solid var(--border-color);
  flex-shrink: 0;
}

.table-header h2 {
  margin: 0 0 10px 0;
  color: var(--text-color);
}

.table-info {
  display: flex;
  gap: 20px;
  font-size: 14px;
  color: var(--text-color);
  opacity: 0.8;
}

.table-summary {
  display: flex;
  gap: 16px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.summary-item {
  padding: 4px 12px;
  border-radius: 16px;
  font-size: 13px;
  font-weight: 500;
}

.summary-trend {
  background-color: #e3f2fd;
  color: #1565c0;
}

.summary-accumulation {
  background-color: #f3e5f5;
  color: #7b1fa2;
}

.summary-distribution {
  background-color: #ffebee;
  color: #c62828;
}

.table-wrapper {
  flex: 1;
  overflow: auto;
  padding: 0 20px 20px 20px;
  min-height: 0;
}

.data-table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background-color: var(--bg-color);
  color: var(--text-color);
}

.data-table thead {
  position: sticky;
  top: 0;
  z-index: 10;
  background-color: var(--bg-color);
}

.data-table th {
  padding: 12px 8px;
  text-align: center;
  font-weight: bold;
  color: var(--text-color);
  border: 1px solid var(--border-color);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  position: relative;
  background-color: var(--bg-color);
}

.data-table th.sortable:hover {
  background-color: var(--hover-color);
}

.sort-icon {
  margin-left: 4px;
  font-size: 12px;
  opacity: 0.7;
}

.data-table th:hover .sort-icon {
  opacity: 1;
}

.data-table td {
  padding: 10px 8px;
  text-align: center;
  font-size: 14px;
  border: 1px solid var(--border-color);
  white-space: nowrap;
}

.data-table tbody tr:hover {
  background-color: var(--hover-color);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

/* 滚动条样式 */
.table-wrapper::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.table-wrapper::-webkit-scrollbar-track {
  background: var(--sidebar-bg);
}

.table-wrapper::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 5px;
}

.table-wrapper::-webkit-scrollbar-thumb:hover {
  background: var(--hover-color);
}
</style>

