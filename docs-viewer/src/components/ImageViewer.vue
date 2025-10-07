<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  imageSrc: {
    type: String,
    required: true
  },
  imageAlt: {
    type: String,
    default: ''
  }
})

const imageContainer = ref(null)
const imageElement = ref(null)
const scale = ref(1)
const minScale = ref(0.1)
const maxScale = ref(5)
const translateX = ref(0)
const translateY = ref(0)
const isDragging = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const isFullscreen = ref(false)
const imageLoaded = ref(false)
const imageError = ref(false)
const imageNaturalWidth = ref(0)
const imageNaturalHeight = ref(0)

// 图片宽高比
const aspectRatio = computed(() => {
  if (imageNaturalHeight.value === 0) return 1
  return imageNaturalWidth.value / imageNaturalHeight.value
})

// 判断是否为超高图片（高度大于宽度的2倍）
const isTallImage = computed(() => aspectRatio.value < 0.5)

// 图片样式
const imageStyle = computed(() => ({
  transform: `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`,
  cursor: isDragging.value ? 'grabbing' : (scale.value > 1 ? 'grab' : 'default'),
  transition: isDragging.value ? 'none' : 'transform 0.2s ease-out'
}))

// 重置视图
const resetView = () => {
  scale.value = 1
  translateX.value = 0
  translateY.value = 0
}

// 缩放
const zoom = (delta, centerX = null, centerY = null) => {
  const oldScale = scale.value
  const newScale = Math.max(minScale.value, Math.min(maxScale.value, oldScale * (1 + delta)))
  
  if (centerX !== null && centerY !== null && imageContainer.value) {
    const rect = imageContainer.value.getBoundingClientRect()
    const offsetX = centerX - rect.left - rect.width / 2
    const offsetY = centerY - rect.top - rect.height / 2
    
    translateX.value = translateX.value - offsetX * (newScale / oldScale - 1)
    translateY.value = translateY.value - offsetY * (newScale / oldScale - 1)
  }
  
  scale.value = newScale
}

// 放大
const zoomIn = () => {
  zoom(0.2)
}

// 缩小
const zoomOut = () => {
  zoom(-0.2)
}

// 适应窗口宽度
const fitWidth = () => {
  if (!imageContainer.value || !imageElement.value) return
  const containerWidth = imageContainer.value.clientWidth
  const imageWidth = imageNaturalWidth.value
  scale.value = (containerWidth * 0.95) / imageWidth
  translateX.value = 0
  translateY.value = 0
}

// 适应窗口高度
const fitHeight = () => {
  if (!imageContainer.value || !imageElement.value) return
  const containerHeight = imageContainer.value.clientHeight
  const imageHeight = imageNaturalHeight.value
  scale.value = (containerHeight * 0.95) / imageHeight
  translateX.value = 0
  translateY.value = 0
}

// 100% 原始尺寸
const actualSize = () => {
  scale.value = 1
  translateX.value = 0
  translateY.value = 0
}

// 鼠标滚轮缩放
const handleWheel = (e) => {
  e.preventDefault()
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  zoom(delta, e.clientX, e.clientY)
}

// 鼠标拖拽开始
const handleMouseDown = (e) => {
  if (scale.value <= 1) return
  isDragging.value = true
  dragStartX.value = e.clientX - translateX.value
  dragStartY.value = e.clientY - translateY.value
}

// 鼠标拖拽移动
const handleMouseMove = (e) => {
  if (!isDragging.value) return
  translateX.value = e.clientX - dragStartX.value
  translateY.value = e.clientY - dragStartY.value
}

// 鼠标拖拽结束
const handleMouseUp = () => {
  isDragging.value = false
}

// 触摸事件支持
let touchStartDistance = 0
let touchStartScale = 1

const getTouchDistance = (touches) => {
  const dx = touches[0].clientX - touches[1].clientX
  const dy = touches[0].clientY - touches[1].clientY
  return Math.sqrt(dx * dx + dy * dy)
}

const handleTouchStart = (e) => {
  if (e.touches.length === 2) {
    e.preventDefault()
    touchStartDistance = getTouchDistance(e.touches)
    touchStartScale = scale.value
  } else if (e.touches.length === 1 && scale.value > 1) {
    isDragging.value = true
    dragStartX.value = e.touches[0].clientX - translateX.value
    dragStartY.value = e.touches[0].clientY - translateY.value
  }
}

const handleTouchMove = (e) => {
  if (e.touches.length === 2) {
    e.preventDefault()
    const currentDistance = getTouchDistance(e.touches)
    const newScale = (currentDistance / touchStartDistance) * touchStartScale
    scale.value = Math.max(minScale.value, Math.min(maxScale.value, newScale))
  } else if (e.touches.length === 1 && isDragging.value) {
    e.preventDefault()
    translateX.value = e.touches[0].clientX - dragStartX.value
    translateY.value = e.touches[0].clientY - dragStartY.value
  }
}

const handleTouchEnd = () => {
  isDragging.value = false
  touchStartDistance = 0
}

// 全屏切换
const toggleFullscreen = () => {
  if (!document.fullscreenElement) {
    imageContainer.value?.requestFullscreen()
    isFullscreen.value = true
  } else {
    document.exitFullscreen()
    isFullscreen.value = false
  }
}

// 图片加载完成
const handleImageLoad = () => {
  imageLoaded.value = true
  imageError.value = false
  if (imageElement.value) {
    imageNaturalWidth.value = imageElement.value.naturalWidth
    imageNaturalHeight.value = imageElement.value.naturalHeight
    
    // 对于超高图片，默认适应宽度
    if (isTallImage.value) {
      fitWidth()
    }
  }
}

// 图片加载错误
const handleImageError = () => {
  imageError.value = true
  imageLoaded.value = false
}

// 监听全屏变化
const handleFullscreenChange = () => {
  isFullscreen.value = !!document.fullscreenElement
}

// 键盘快捷键
const handleKeyDown = (e) => {
  if (e.key === 'Escape' && isFullscreen.value) {
    toggleFullscreen()
  } else if (e.key === '+' || e.key === '=') {
    zoomIn()
  } else if (e.key === '-') {
    zoomOut()
  } else if (e.key === '0') {
    resetView()
  } else if (e.key === 'f' || e.key === 'F') {
    toggleFullscreen()
  }
}

// 监听图片源变化，重置视图
watch(() => props.imageSrc, () => {
  resetView()
  imageLoaded.value = false
  imageError.value = false
})

onMounted(() => {
  document.addEventListener('fullscreenchange', handleFullscreenChange)
  document.addEventListener('keydown', handleKeyDown)
  window.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('mouseup', handleMouseUp)
})

onUnmounted(() => {
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
  document.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('mouseup', handleMouseUp)
})
</script>

<template>
  <div class="image-viewer-container" :class="{ 'fullscreen': isFullscreen }">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-info">
        <span v-if="imageLoaded" class="image-info">
          {{ imageNaturalWidth }} × {{ imageNaturalHeight }} px
          <span v-if="isTallImage" class="tall-badge">超高图片</span>
        </span>
        <span class="zoom-level">{{ Math.round(scale * 100) }}%</span>
      </div>
      <div class="toolbar-buttons">
        <button @click="zoomOut" title="缩小 (-)">🔍-</button>
        <button @click="zoomIn" title="放大 (+)">🔍+</button>
        <button @click="resetView" title="重置 (0)">↺</button>
        <button @click="fitWidth" title="适应宽度">↔️</button>
        <button @click="fitHeight" title="适应高度">↕️</button>
        <button @click="actualSize" title="实际大小">1:1</button>
        <button @click="toggleFullscreen" title="全屏 (F)">
          {{ isFullscreen ? '⛶' : '⛶' }}
        </button>
      </div>
    </div>

    <!-- 图片容器 -->
    <div 
      ref="imageContainer"
      class="image-container"
      @wheel="handleWheel"
      @mousedown="handleMouseDown"
      @touchstart="handleTouchStart"
      @touchmove="handleTouchMove"
      @touchend="handleTouchEnd"
    >
      <div v-if="!imageLoaded && !imageError" class="loading">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>
      
      <div v-if="imageError" class="error">
        <p>❌ 图片加载失败</p>
        <p class="error-detail">{{ imageSrc }}</p>
      </div>
      
      <img
        ref="imageElement"
        :src="imageSrc"
        :alt="imageAlt"
        :style="imageStyle"
        @load="handleImageLoad"
        @error="handleImageError"
        class="viewer-image"
        :class="{ 'loaded': imageLoaded }"
      />
    </div>

    <!-- 提示信息 -->
    <div v-if="imageLoaded && isTallImage && scale === 1" class="hint">
      💡 提示：这是一张超高图片，建议使用滚轮缩放或点击"适应宽度"按钮查看完整内容
    </div>
  </div>
</template>

<style scoped>
.image-viewer-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background-color: var(--bg-color);
  position: relative;
  overflow: hidden;
}

.image-viewer-container.fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 9999;
  background-color: #000;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background-color: var(--sidebar-bg);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
  gap: 15px;
  flex-wrap: wrap;
}

.toolbar-info {
  display: flex;
  gap: 15px;
  align-items: center;
  flex-wrap: wrap;
}

.image-info {
  font-size: 13px;
  color: var(--text-color);
  display: flex;
  align-items: center;
  gap: 8px;
}

.tall-badge {
  background: #ff6b6b;
  color: white;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.zoom-level {
  font-size: 14px;
  font-weight: 600;
  color: #1976d2;
  min-width: 50px;
}

.toolbar-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-buttons button {
  padding: 6px 12px;
  background-color: var(--bg-color);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-color);
  transition: all 0.2s;
  white-space: nowrap;
}

.toolbar-buttons button:hover {
  background-color: var(--hover-color);
  border-color: #1976d2;
  transform: translateY(-1px);
}

.toolbar-buttons button:active {
  transform: translateY(0);
}

.image-container {
  flex: 1;
  overflow: hidden;
  display: flex;
  justify-content: center;
  align-items: center;
  position: relative;
  background: 
    linear-gradient(45deg, var(--sidebar-bg) 25%, transparent 25%),
    linear-gradient(-45deg, var(--sidebar-bg) 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, var(--sidebar-bg) 75%),
    linear-gradient(-45deg, transparent 75%, var(--sidebar-bg) 75%);
  background-size: 20px 20px;
  background-position: 0 0, 0 10px, 10px -10px, -10px 0px;
}

.viewer-image {
  max-width: none;
  max-height: none;
  user-select: none;
  -webkit-user-drag: none;
  opacity: 0;
  transition: opacity 0.3s;
}

.viewer-image.loaded {
  opacity: 1;
}

.loading, .error {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: var(--text-color);
}

.spinner {
  width: 50px;
  height: 50px;
  border: 4px solid var(--border-color);
  border-top-color: #1976d2;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 15px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error {
  color: #ff6b6b;
}

.error-detail {
  font-size: 12px;
  color: var(--text-color);
  opacity: 0.7;
  margin-top: 8px;
  word-break: break-all;
  max-width: 400px;
}

.hint {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(25, 118, 210, 0.9);
  color: white;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 13px;
  max-width: 90%;
  text-align: center;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  animation: fadeIn 0.5s ease-out;
  z-index: 10;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .toolbar {
    padding: 8px 12px;
  }
  
  .toolbar-buttons button {
    padding: 4px 8px;
    font-size: 12px;
  }
  
  .hint {
    font-size: 11px;
    padding: 8px 12px;
    bottom: 10px;
  }
}
</style>

