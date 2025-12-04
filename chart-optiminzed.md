# 图表可视化优化方案 (Chart Optimization Plan)

针对“时间跨度长、代币数量多”的场景，当前的图表实现存在性能瓶颈和视觉混乱的问题。以下是针对 `VolumeChartEcharts.vue` 和 `ChartView.vue` 的优化方案。

## 1. 核心问题分析

1.  **视觉干扰 (Visual Clutter)**: 当展示数十甚至上百个 Token 的趋势线时，图表会变成“意大利面条”，难以分辨具体趋势。
2.  **性能瓶颈 (Performance)**: ECharts 渲染过多的 Series（线条）和 DOM 节点（Tooltip、Legend）会导致页面卡顿，交互响应慢。
3.  **图例不可用 (Legend Overload)**: 默认的图例在 Token 数量多时会占据大量空间，且难以快速找到特定 Token。
4.  **颜色区分度低**: 颜色数量有限，多条线颜色重复，无法区分。

## 2. 优化策略

### 策略 A: "概览 + 聚焦" 模式 (Overview + Focus)

不要一次性展示所有 Token。默认只展示“Top N”或“总览”，让用户主动选择感兴趣的 Token。

#### 1. 智能默认选中 (Smart Default Selection)
*   **现状**: `selectAllTokens` 默认选中所有符合过滤条件的 Token。
*   **优化**: 初始化时，仅默认选中 **交易量最大 (Top 10)** 或 **波动最大** 的 Token。
*   **实现**: 修改 `availableTokens` 逻辑，增加 `topTokens` 计算属性，初始化 `selectedTokens` 时只取前 10 个。

#### 2. 增强型 Token 选择器 (Advanced Token Selector)
*   **现状**: 简单的 Platform 标签过滤。
*   **优化**: 移除 ECharts 原生 Legend（或仅保留少量），使用自定义的 **侧边栏/抽屉式 Token 列表**。
    *   **功能**: 支持搜索、按交易量排序、按涨跌幅排序。
    *   **交互**: 列表项包含 Checkbox，用户勾选后才在图表中显示该 Token 的线。
    *   **虚拟滚动**: 如果 Token 数量上千，使用虚拟滚动 (Virtual Scrolling) 优化列表渲染。

### 策略 B: 视觉与交互优化 (Visual & Interaction)

#### 3. 性能模式配置 (Performance Mode)
当显示的线条数量超过阈值（如 > 20 条）时，自动降级渲染效果：
*   **关闭数据点图标**: 设置 `symbol: 'none'`，仅显示线条。
*   **开启降采样**: 设置 `sampling: 'lttb'` (Largest-Triangle-Three-Buckets)，减少绘制点数，保持趋势特征。
*   **线条变细**: 减少 `lineStyle.width`。

#### 4. 优化 Tooltip (Tooltip Optimization)
*   **现状**: Tooltip 会列出所有 Series 的数据，导致遮挡屏幕。
*   **优化**:
    *   **排序**: Tooltip 内的数据按当前鼠标位置的数值 **降序排列**。
    *   **截断**: 仅显示 Top 10-15 的数据，剩余的显示为 "Others..."。
    *   **固定位置**: 考虑将 Tooltip 信息固定在图表侧边栏，而不是跟随鼠标。

#### 5. 引入“热力图”模式 (Heatmap Mode - 可选)
对于极大量 Token 的宏观观察，折线图不再适用。建议增加一个切换按钮，切换到 **热力图 (Heatmap)** 视图：
*   **X轴**: 时间
*   **Y轴**: Token 名称（按交易量排序）
*   **颜色**: 交易量大小（或涨跌幅）
*   **优势**: 可以一眼看出哪些 Token 在哪些时间段活跃。

### 策略 C: 数据处理优化 (Data Processing)

#### 6. 数据聚合 (Data Aggregation)
*   如果时间跨度非常长（如 > 1 年），且用户未进行缩放（Zoom），前端可对数据进行 **周粒度** 或 **月粒度** 聚合（求平均或求和），减少渲染点数。当用户放大（Zoom In）时，再动态切换回日粒度数据。

## 3. 具体实施步骤 (Implementation Steps)

### 第一阶段：基础体验优化 (快速见效)
1.  **修改默认行为**: `onMounted` 中不再 `selectAllTokens`，改为 `selectTopTokens(10)`。
2.  **优化 ECharts 配置**:
    *   为 Series 开启 `sampling: 'lttb'`。
    *   当 `selectedTokens.length > 20` 时，动态设置 `symbol: 'none'`。
3.  **优化 Tooltip**: 修改 `formatter`，对 `params` 进行排序并限制显示数量（如最多 15 行）。

### 第二阶段：交互重构 (解决多 Token 选择)
1.  **重构控制栏**: 将原本的 Platform 过滤和 MinVolume 滑动条整合到一个更高级的“数据控制面板”中。
2.  **实现自定义图例列表**:
    *   在图表右侧（或左侧）增加一个可滚动的列表区域。
    *   列出所有可用 Token，显示其最新交易量。
    *   提供“全选/反选”、“仅看 Top 10”等快捷按钮。
    *   与 ECharts 的 `legend` 联动（或完全替代 `legend`）。

### 第三阶段：高级视图 (可选)
1.  **添加视图切换**: [折线图] / [热力图]。
2.  **实现热力图组件**: 使用 ECharts Heatmap 展示 `Token x Time` 的交易量分布。

## 4. 代码结构调整建议

建议将 `VolumeChartEcharts.vue` 拆分为：
*   `ChartControlPanel.vue`: 负责筛选、排序、Token 列表选择。
*   `ChartDisplay.vue`: 纯粹的 ECharts 包装，只负责渲染传入的数据。
*   `useChartData.js`: 抽离数据处理逻辑（排序、过滤、聚合）。

---

**总结**: 核心思路是从“展示所有数据”转变为“提供探索数据的工具”。通过默认展示 Top N 和提供强大的筛选列表，解决“多 Token”问题；通过降采样和样式简化，解决“长跨度”带来的性能问题。
