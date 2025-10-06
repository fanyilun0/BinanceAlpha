<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  tableData: {
    type: [Object, Array],
    required: true
  }
})

const sortColumn = ref('')
const sortDirection = ref('asc') // 'asc' or 'desc'

// 判断是否为原始数组数据（filtered_crypto_list 格式）
const isRawData = computed(() => {
  return Array.isArray(props.tableData)
})

// 转换原始数据为表格格式
const formattedTableData = computed(() => {
  if (isRawData.value) {
    // 原始数据格式，需要转换
    const data = props.tableData.map(item => {
      const usdQuote = item.quotes?.find(q => q.name === 'USD')
      return {
        '排名': item.cmcRank || '-',
        '名称': item.name || '-',
        '代号': item.symbol || '-',
        '价格(USD)': usdQuote?.price ? `$${usdQuote.price.toFixed(6)}` : '-',
        '24h变化(%)': usdQuote?.percentChange24h ? usdQuote.percentChange24h.toFixed(2) : '-',
        '7d变化(%)': usdQuote?.percentChange7d ? usdQuote.percentChange7d.toFixed(2) : '-',
        '市值': usdQuote?.marketCap ? `$${(usdQuote.marketCap / 1000000).toFixed(2)}M` : '-',
        '24h交易量': usdQuote?.volume24h ? `$${(usdQuote.volume24h / 1000000).toFixed(2)}M` : '-',
        '流通量': item.circulatingSupply ? item.circulatingSupply.toLocaleString() : '-',
        '平台': item.platform?.name || '-',
        '标签': item.tags?.join(', ') || '-'
      }
    })
    
    return {
      title: '加密货币列表',
      date: new Date().toLocaleDateString('zh-CN'),
      total_count: data.length,
      columns: ['排名', '名称', '代号', '价格(USD)', '24h变化(%)', '7d变化(%)', '市值', '24h交易量', '流通量', '平台', '标签'],
      data: data
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

// 获取单元格颜色
const getCellColor = (row, column) => {
  // 24h变化(%) 列
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
  
  // 合约列
  if (column === '合约' && row[column] === '是') {
    return '#e0f7fa' // 浅蓝色
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
  padding: 20px;
  height: 100%;
  overflow: auto;
}

.table-header {
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 2px solid var(--border-color);
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

.table-wrapper {
  overflow-x: auto;
  overflow-y: auto;
  max-height: calc(100vh - 200px);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background-color: var(--bg-color);
  color: var(--text-color);
}

.data-table thead {
  position: sticky;
  top: 0;
  z-index: 10;
  background-color: #2a9d8f;
}

.data-table th {
  padding: 12px 8px;
  text-align: center;
  font-weight: bold;
  color: white;
  border: 1px solid #1a7a6f;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  position: relative;
}

.data-table th.sortable:hover {
  background-color: #248277;
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
  border: 1px solid var(--border-color);
  white-space: nowrap;
}

.data-table tbody tr:nth-child(even) {
  background-color: var(--hover-color);
}

.data-table tbody tr:hover {
  background-color: var(--active-color);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
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

