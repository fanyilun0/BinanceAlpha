<script setup>
import { ref, computed, onMounted } from 'vue'
import MarkdownViewer from './components/MarkdownViewer.vue'
import TableViewer from './components/TableViewer.vue'

const files = ref([])
const images = ref([])
const tables = ref([])
const currentTab = ref('docs') // 'docs', 'images', or 'tables'
const currentImageTab = ref('alpha_list') // 'alpha_list', 'vol_mc_ratio', or 'gainers_losers'
const currentTableTab = ref('alpha_list') // 'alpha_list', 'vol_mc_ratio', 'gainers_losers', 'top_gainers', 'top_losers'
const currentFile = ref('')
const currentContent = ref('')
const currentImage = ref('')
const currentTable = ref('')
const currentTableData = ref(null)
const searchQuery = ref('')
const isDarkMode = ref(false)
const isLoading = ref(false)

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

// 按类型分组表格
const tablesByType = computed(() => {
  const grouped = {
    alpha_list: [],
    vol_mc_ratio: [],
    gainers_losers: [],
    top_gainers: [],
    top_losers: [],
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
}

const switchImageTab = (tab) => {
  currentImageTab.value = tab
  searchQuery.value = '' // 切换图片子标签时清空搜索
  currentImage.value = '' // 清空当前选中的图片
}

const switchTableTab = (tab) => {
  currentTableTab.value = tab
  searchQuery.value = '' // 切换表格子标签时清空搜索
  currentTable.value = '' // 清空当前选中的表格
  currentTableData.value = null
}

const toggleDarkMode = () => {
  isDarkMode.value = !isDarkMode.value
  document.documentElement.classList.toggle('dark-mode')
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
        <button class="theme-toggle" @click="toggleDarkMode">
          {{ isDarkMode ? '🌞' : '🌙' }}
        </button>
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
      
      <!-- 搜索框：仅在文档和图片标签页显示 -->
      <div v-if="currentTab !== 'tables'" class="search-box">
        <input 
          type="text" 
          v-model="searchQuery"
          :placeholder="currentTab === 'docs' ? '搜索文档...' : '搜索图片...'"
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
      <div v-else-if="currentImage && currentTab === 'images'" class="image-viewer">
        <img :src="`/images/${currentImage}`" :alt="currentImage" />
      </div>
      
      <div v-else class="no-content">
        请选择要查看的{{ currentTab === 'docs' ? '文档' : currentTab === 'tables' ? '数据表格' : '图片' }}
      </div>
    </div>
  </div>
</template>

<style>
:root {
  --bg-color: #ffffff;
  --text-color: #24292e;
  --sidebar-bg: #f5f5f5;
  --border-color: #ddd;
  --hover-color: #e0e0e0;
  --active-color: #e0e0e0;
}

.dark-mode {
  --bg-color: #1a1a1a;
  --text-color: #e0e0e0;
  --sidebar-bg: #2d2d2d;
  --border-color: #404040;
  --hover-color: #404040;
  --active-color: #505050;
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
}

.app-container {
  display: flex;
  height: 100vh;
  background-color: var(--bg-color);
  color: var(--text-color);
  overflow: hidden;
}

.sidebar {
  width: 400px;
  min-width: 400px;
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
  overflow-y: auto;
  padding: 0;
  position: relative;
  background-color: var(--bg-color);
  width: 1200px;
  min-width: 1200px;
  max-width: 1200px;
  margin: 0 auto;
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

.image-viewer {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  height: 100%;
  overflow: auto;
}

.image-viewer img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
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
