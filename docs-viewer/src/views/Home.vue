<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import MarkdownViewer from '../components/MarkdownViewer.vue'
import TableViewer from '../components/TableViewer.vue'
import ImageViewer from '../components/ImageViewer.vue'

const router = useRouter()

const files = ref([])
const images = ref([])
const tables = ref([])
const currentTab = ref('docs') // 'docs', 'images', or 'tables'
const currentImageTab = ref('alpha_list') // 'alpha_list', 'vol_mc_ratio', or 'gainers_losers'
const currentTableTab = ref('crypto_list') // 'crypto_list' or 'trend_signals'
const currentFile = ref('')
const currentContent = ref('')
const currentImage = ref('')
const currentTable = ref('')
const currentTableData = ref(null)
const searchQuery = ref('')
const isDarkMode = ref(false)
const isLoading = ref(false)

// 按类型分组表格 (使用 list.json 中的 type 字段)
const tablesByType = computed(() => {
  const grouped = {
    crypto_list: [],      // filtered_crypto_list_*.json
    trend_signals: [],    // trend_signals_*.json
    other: []
  }
  
  tables.value.forEach(table => {
    const type = table.type || 'other'
    if (grouped[type]) {
      grouped[type].push(table)
    } else {
      grouped.other.push(table)
    }
  })
  
  return grouped
})

// 按类型分组图片
const imagesByType = computed(() => {
  const grouped = {
    alpha_list: [],
    vol_mc_ratio: [],
    gainers_losers: [],
    other: []
  }
  
  images.value.forEach(img => {
    const type = img.type || 'other'
    if (grouped[type]) {
      grouped[type].push(img)
    } else {
      grouped.other.push(img)
    }
  })
  
  return grouped
})


// 搜索过滤 - 根据当前标签页过滤
const filteredItems = computed(() => {
  if (currentTab.value === 'docs') {
    const items = files.value
    if (!searchQuery.value) return items
    const query = searchQuery.value.toLowerCase()
    return items.filter(item => 
      item.title.toLowerCase().includes(query) || 
      (item.name && item.name.toLowerCase().includes(query))
    )
  } else if (currentTab.value === 'images') {
    // 图片标签页：根据当前子标签页过滤
    const items = imagesByType.value[currentImageTab.value] || []
    if (!searchQuery.value) return items
    const query = searchQuery.value.toLowerCase()
    return items.filter(item => 
      item.title.toLowerCase().includes(query) || 
      (item.name && item.name.toLowerCase().includes(query))
    )
  } else {
    // 表格标签页：根据当前子标签页过滤
    const items = tablesByType.value[currentTableTab.value] || []
    if (!searchQuery.value) return items
    const query = searchQuery.value.toLowerCase()
    return items.filter(item => 
      item.title.toLowerCase().includes(query) || 
      (item.name && item.name.toLowerCase().includes(query))
    )
  }
})

const selectFile = async (file) => {
  if (currentFile.value === file.name) return
  currentFile.value = file.name
  currentImage.value = '' // 清空图片选择
  currentTable.value = '' // 清空表格选择
  currentTableData.value = null
  isLoading.value = true
  try {
    const response = await fetch(`/advices/${file.name}`)
    currentContent.value = await response.text()
  } catch (error) {
    console.error('Error loading file:', error)
    currentContent.value = '加载文件时出错'
  } finally {
    isLoading.value = false
  }
}

const selectImage = (image) => {
  if (currentImage.value === image.name) return
  currentImage.value = image.name
  currentFile.value = '' // 清空文档选择
  currentContent.value = '' // 清空文档内容
  currentTable.value = '' // 清空表格选择
  currentTableData.value = null
}

const selectTable = async (table) => {
  if (currentTable.value === table.name) return
  currentTable.value = table.name
  currentFile.value = '' // 清空文档选择
  currentContent.value = '' // 清空文档内容
  currentImage.value = '' // 清空图片选择
  isLoading.value = true
  try {
    const response = await fetch(`/tables/${table.name}`)
    currentTableData.value = await response.json()
  } catch (error) {
    console.error('Error loading table:', error)
    currentTableData.value = null
  } finally {
    isLoading.value = false
  }
}

const switchTab = (tab) => {
  currentTab.value = tab
  searchQuery.value = '' // 切换标签时清空搜索
  
  // 切换tab时默认选中第一个数据来预览
  if (tab === 'docs' && files.value.length > 0) {
    selectFile(files.value[0])
  } else if (tab === 'tables' && tablesByType.value[currentTableTab.value]?.length > 0) {
    selectTable(tablesByType.value[currentTableTab.value][0])
  } else if (tab === 'images' && imagesByType.value[currentImageTab.value]?.length > 0) {
    selectImage(imagesByType.value[currentImageTab.value][0])
  }
}

const switchTableTab = (tab) => {
  currentTableTab.value = tab
  searchQuery.value = '' // 切换表格子标签时清空搜索
  
  // 切换表格子标签时默认选中第一个表格
  if (tablesByType.value[tab]?.length > 0) {
    selectTable(tablesByType.value[tab][0])
  } else {
    currentTable.value = '' // 如果没有表格，清空当前选中
    currentTableData.value = null
  }
}

const switchImageTab = (tab) => {
  currentImageTab.value = tab
  searchQuery.value = '' // 切换图片子标签时清空搜索
  
  // 切换图片子标签时默认选中第一个图片
  if (imagesByType.value[tab]?.length > 0) {
    selectImage(imagesByType.value[tab][0])
  } else {
    currentImage.value = '' // 如果没有图片，清空当前选中
  }
}

const toggleDarkMode = () => {
  isDarkMode.value = !isDarkMode.value
  document.documentElement.classList.toggle('dark-mode')
}

const goToChartView = () => {
  router.push('/chart')
}

onMounted(async () => {
  try {
    const response = await fetch('/advices/list.json')
    const data = await response.json()
    files.value = data.files?.sort((a, b) => b.name.localeCompare(a.name)) || []
    images.value = data.images?.sort((a, b) => b.name.localeCompare(a.name)) || []
    tables.value = data.tables?.sort((a, b) => b.name.localeCompare(a.name)) || []
    
    // 默认选中第一个文件（最新的）
    if (files.value.length > 0) {
      selectFile(files.value[0])
    }
  } catch (error) {
    console.error('Error fetching files:', error)
  }
})
</script>

<template>
  <div class="app-container" :class="{ 'dark': isDarkMode }">
    <div class="sidebar">
      <div class="sidebar-header">
        <h2>资源浏览</h2>
        <div class="header-actions">
          <button @click="goToChartView" class="chart-link" title="查看交易量图表">
            📈
          </button>
          <a 
            href="https://github.com/fanyilun0/BinanceAlpha" 
            target="_blank" 
            rel="noopener noreferrer"
            class="github-link"
            title="GitHub Repository"
          >
            <svg height="24" width="24" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
            </svg>
          </a>
          <button class="theme-toggle" @click="toggleDarkMode">
            {{ isDarkMode ? '🌞' : '🌙' }}
          </button>
        </div>
      </div>
      
      <!-- Tab 切换按钮 -->
      <div class="tab-buttons">
        <button 
          :class="{ active: currentTab === 'docs' }" 
          @click="switchTab('docs')"
        >
          📄 文档 ({{ files.length }})
        </button>
        <button 
          :class="{ active: currentTab === 'tables' }" 
          @click="switchTab('tables')"
        >
          📊 表格 ({{ tables.length }})
        </button>
        <button 
          :class="{ active: currentTab === 'images' }" 
          @click="switchTab('images')"
        >
          🖼️ 图片 ({{ images.length }})
        </button>
      </div>
      
      <!-- 图片子标签 (仅在图片标签页时显示) -->
      <div v-if="currentTab === 'images'" class="sub-tabs">
        <button 
          :class="{ active: currentImageTab === 'alpha_list' }" 
          @click="switchImageTab('alpha_list')"
        >
          📊 Alpha项目列表 ({{ imagesByType.alpha_list.length }})
        </button>
        <button 
          :class="{ active: currentImageTab === 'vol_mc_ratio' }" 
          @click="switchImageTab('vol_mc_ratio')"
        >
          💧 高流动性项目 ({{ imagesByType.vol_mc_ratio.length }})
        </button>
        <button 
          :class="{ active: currentImageTab === 'gainers_losers' }" 
          @click="switchImageTab('gainers_losers')"
        >
          📈 涨跌幅榜 ({{ imagesByType.gainers_losers.length }})
        </button>
      </div>
      
      <!-- 表格子标签 (仅在表格标签页时显示) -->
      <div v-if="currentTab === 'tables'" class="sub-tabs">
        <button 
          :class="{ active: currentTableTab === 'crypto_list' }" 
          @click="switchTableTab('crypto_list')"
        >
          📋 加密货币列表 ({{ tablesByType.crypto_list.length }})
        </button>
        <button 
          :class="{ active: currentTableTab === 'trend_signals' }" 
          @click="switchTableTab('trend_signals')"
        >
          🐋 吸筹/洗盘信号 ({{ tablesByType.trend_signals.length }})
        </button>
      </div>

      
      <!-- 搜索框：在所有标签页显示 -->
      <div class="search-box">
        <input 
          type="text" 
          v-model="searchQuery"
          :placeholder="currentTab === 'docs' ? '搜索文档...' : currentTab === 'tables' ? '搜索表格...' : '搜索图片...'"
        >
      </div>
      
      <!-- 文档列表 -->
      <ul v-if="currentTab === 'docs'" class="file-list">
        <li 
          v-for="file in filteredItems" 
          :key="file.name"
          :class="{ active: currentFile === file.name }"
          @click="selectFile(file)"
        >
          {{ file.name.replace('.md', '') }}
        </li>
      </ul>
      
      <!-- 表格列表 -->
      <ul v-else-if="currentTab === 'tables'" class="file-list">
        <li 
          v-for="table in filteredItems" 
          :key="table.name"
          :class="{ active: currentTable === table.name }"
          @click="selectTable(table)"
        >
          {{ table.name.replace('.json', '') }}
        </li>
      </ul>
      
      <!-- 图片列表 -->
      <ul v-else class="file-list">
        <li 
          v-for="image in filteredItems" 
          :key="image.name"
          :class="{ active: currentImage === image.name }"
          @click="selectImage(image)"
        >
          {{ image.name.replace('.png', '') }}
        </li>
      </ul>
    </div>
    
    <div class="content">
      <div v-if="isLoading" class="loading">
        加载中...
      </div>
      
      <!-- 文档内容 -->
      <MarkdownViewer 
        v-else-if="currentContent && currentTab === 'docs'" 
        :content="currentContent"
      />
      
      <!-- 表格内容 -->
      <TableViewer 
        v-else-if="currentTableData && currentTab === 'tables'" 
        :tableData="currentTableData"
      />
      
      <!-- 图片内容 -->
      <ImageViewer 
        v-else-if="currentImage && currentTab === 'images'" 
        :imageSrc="`/images/${currentImage}`"
        :imageAlt="currentImage"
      />
      
      <div v-else class="no-content">
        请选择要查看的{{ currentTab === 'docs' ? '文档' : currentTab === 'tables' ? '数据表格' : '图片' }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  background-color: var(--bg-color);
  color: var(--text-color);
  overflow: hidden;
  margin: 0;
  padding: 0;
}

.sidebar {
  width: 440px;
  background-color: var(--sidebar-bg);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  transition: all 0.3s ease;
  overflow: hidden;
}

.sidebar-header {
  padding: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.chart-link {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 5px 10px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 1.2em;
  transition: all 0.2s;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.chart-link:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

.github-link {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 5px;
  color: var(--text-color);
  text-decoration: none;
  border-radius: 5px;
  transition: all 0.2s;
  opacity: 0.8;
}

.github-link:hover {
  background-color: var(--hover-color);
  opacity: 1;
}

.github-link svg {
  width: 24px;
  height: 24px;
}

.tab-buttons {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.tab-buttons button {
  flex: 1;
  padding: 12px 16px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-color);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
  white-space: nowrap;
}

.tab-buttons button:hover {
  background-color: var(--hover-color);
}

.tab-buttons button.active {
  border-bottom-color: #1976d2;
  color: #1976d2;
  font-weight: 600;
}

.sub-tabs {
  display: flex;
  flex-direction: column;
  gap: 0;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
  background-color: var(--sidebar-bg);
}

.sub-tabs button {
  padding: 10px 16px;
  background: none;
  border: none;
  border-left: 3px solid transparent;
  color: var(--text-color);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
  text-align: left;
}

.sub-tabs button:hover {
  background-color: var(--hover-color);
}

.sub-tabs button.active {
  border-left-color: #1976d2;
  background-color: var(--active-color);
  color: #1976d2;
  font-weight: 600;
}

.sidebar h2 {
  margin: 0;
  color: var(--text-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.theme-toggle {
  background: none;
  border: none;
  font-size: 1.5em;
  cursor: pointer;
  padding: 5px;
  border-radius: 5px;
  transition: background-color 0.2s;
}

.theme-toggle:hover {
  background-color: var(--hover-color);
}

.search-box {
  padding: 15px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.search-box input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background-color: var(--bg-color);
  color: var(--text-color);
  box-sizing: border-box;
}

.file-list {
  list-style: none;
  padding: 0;
  margin: 0;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.file-list li {
  padding: 12px 20px;
  text-align: left;
  cursor: pointer;
  border-bottom: 1px solid var(--border-color);
  transition: background-color 0.2s, color 0.2s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  position: relative;
}

.file-list li:hover {
  background-color: var(--hover-color);
}

.file-list li.active {
  background-color: var(--active-color);
  color: #1976d2;
}

.file-list li.active::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 4px;
  background: #1976d2;
  border-radius: 0 2px 2px 0;
}

.content {
  flex: 1;
  overflow: hidden;
  padding: 0;
  position: relative;
  background-color: var(--bg-color);
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 1.2em;
  color: var(--text-color);
  white-space: nowrap;
}

.no-content {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  color: var(--text-color);
  font-size: 1.2em;
  padding: 20px;
  text-align: center;
}

@media (max-width: 768px) {
  .sidebar {
    width: 300px;
    min-width: 300px;
  }
}

@media (max-width: 480px) {
  .app-container {
    flex-direction: column;
  }
  
  .sidebar {
    width: 100%;
    min-width: 100%;
    height: auto;
    max-height: 40vh;
  }
  
  .content {
    height: 60vh;
  }
}
</style>
