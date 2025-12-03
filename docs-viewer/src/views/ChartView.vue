<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import VolumeChartEcharts from '../components/VolumeChartEcharts.vue'

const router = useRouter()
const chartData = ref(null)
const isLoading = ref(true)
const isDarkMode = ref(false)

const loadChartData = async () => {
  try {
    const response = await fetch('/charts/volume_time_series.json')
    chartData.value = await response.json()
  } catch (error) {
    console.error('Error loading chart data:', error)
  } finally {
    isLoading.value = false
  }
}

const toggleDarkMode = () => {
  isDarkMode.value = !isDarkMode.value
  document.documentElement.classList.toggle('dark-mode')
}

const goBack = () => {
  router.push('/')
}

onMounted(() => {
  loadChartData()
})
</script>

<template>
  <div class="chart-view" :class="{ 'dark': isDarkMode }">
    <div class="chart-view-header">
      <div class="header-left">
        <button @click="goBack" class="back-btn">
          ← 返回
        </button>
        <h1>Token 交易量趋势分析</h1>
      </div>
      <div class="header-actions">
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
    
    <div class="chart-view-content">
      <div v-if="isLoading" class="loading">
        <div class="loading-spinner"></div>
        <span>加载图表数据中...</span>
      </div>
      <VolumeChartEcharts 
        v-else-if="chartData"
        :chartData="chartData"
      />
      <div v-else class="error">
        加载图表数据失败
      </div>
    </div>
  </div>
</template>

<style scoped>
.chart-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background-color: var(--bg-color);
  color: var(--text-color);
  overflow: hidden;
}

.chart-view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-color);
  background-color: var(--sidebar-bg);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  padding: 8px 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.back-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

.chart-view-header h1 {
  margin: 0;
  font-size: 18px;
  color: var(--text-color);
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
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

.chart-view-content {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 15px;
  color: var(--text-color);
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border-color);
  border-top-color: #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.error {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 1.2em;
  color: #f44336;
}

@media (max-width: 768px) {
  .chart-view-header {
    flex-direction: column;
    gap: 10px;
    align-items: flex-start;
  }
  
  .header-left {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  
  .chart-view-header h1 {
    font-size: 16px;
  }
}
</style>
