# 币安Alpha市场监控与智能分析系统

一个强大的加密货币监控工具，专注于币安Alpha市场分析，提供实时数据收集、上币信息跟踪、市场情绪分析和AI辅助投资建议。

## 核心功能

### 📊 数据收集与分析
- ✅ 实时获取并分析币安Alpha市场项目列表（来自CoinMarketCap API）
- ✅ 自动检测并跟踪币安现货和合约交易对
- ✅ 支持多区块链平台分析（Ethereum、BNB Chain、Solana、Base等）
- ✅ 智能识别1000x格式代币（如1000SATS、1000CAT等）
- ✅ 按区块链平台自动分类整理加密货币项目数据

### 🤖 AI智能投资建议
- ✅ 集成DeepSeek AI模型提供智能投资建议
- ✅ 按区块链平台分类生成专业投资分析报告
- ✅ 多维度数据分析（市值、交易量、价格变化、流动性等）
- ✅ 支持并行处理多个平台的分析任务

### 📈 可视化图表生成
- ✅ 自动生成Alpha项目排名榜图片（按市值排序）
- ✅ 高流动性项目图片（按VOL/MC比值排序）
- ✅ 涨跌幅榜图片（24小时价格变化分析）
- ✅ 图片自动推送至WebHook接收端

### 🌐 Web可视化界面
- ✅ 内置Vue.js文档查看器（`docs-viewer`）
- ✅ 支持查看历史投资建议报告
- ✅ 分类展示不同类型的分析图片
- ✅ 响应式设计，支持深色/浅色主题切换

### 🔧 技术特性
- ✅ 完善的代理配置支持，确保全球范围内稳定访问
- ✅ 进程内缓存机制，避免重复API请求
- ✅ 支持Docker化部署，便于快速搭建和维护
- ✅ 异步并发处理，提高数据获取和分析效率
- ✅ 完整的日志记录系统

## 系统要求

- Python 3.7+
- 互联网连接（用于获取最新市场数据）
- 支持代理服务器配置
- DeepSeek API密钥（用于AI分析功能）

## 安装

1. 克隆本仓库：

```bash
git clone https://github.com/yourusername/BinanceAlpha.git
cd BinanceAlpha
```

2. 安装依赖包：

```bash
pip install -r requirements.txt
```

3. 配置环境变量，创建`.env`文件：

```bash
WEBHOOK_URL=your_webhook_url_here
DEEPSEEK_API_KEY=your_api_key_here
```

## 使用方法

### 基本命令

```bash
# 运行完整工作流（获取数据 + 生成图片 + AI分析）
python main.py

# 调试模式（仅生成提示词不发送API请求）
python main.py --debug-only

# 查看帮助信息
python main.py --help
```

### 工作流说明

系统运行时会依次执行以下步骤：

1. **获取并更新Binance交易对列表**
   - 从币安API获取现货交易对（Spot Symbols）
   - 从币安API获取合约交易对（Futures Symbols）
   - 提取并缓存所有上线的Token名称

2. **获取币安Alpha项目列表数据**
   - 从CoinMarketCap获取币安Alpha项目数据
   - 生成三类分析图片：
     - Alpha项目排名榜（按市值排序）
     - 高流动性项目（按VOL/MC比值排序）
     - 涨跌幅榜（24小时价格变化）
   - 推送图片到WebHook

3. **分类项目并生成投资建议**
   - 按区块链平台分类Alpha项目
   - 过滤已上线币安的项目
   - 并行为每个平台生成AI投资建议
   - 保存建议报告到`advices`目录

### Docker部署

本项目支持Docker部署，使用以下命令快速启动：

```bash
# 构建Docker镜像
docker-compose build

# 启动服务
docker-compose up -d
```

## 配置选项

在`config.py`文件中，您可以自定义以下配置：

- **代理设置**：配置`PROXY_URL`和`USE_PROXY`实现全球稳定访问
- **区块链平台**：在`BLOCKCHAIN_PLATFORMS`中添加或修改支持的区块链平台
- **AI模型参数**：调整`DEEPSEEK_AI`配置优化AI分析效果
- **WebHook**：配置`WEBHOOK_URL`实现数据推送
- **数据目录**：通过`DATA_DIRS`自定义各类数据存储位置

## 数据分析能力

### 币安Alpha项目分析

- **项目基础信息**：名称、代码、排名、区块链平台
- **市场数据**：价格、市值、FDV（完全稀释估值）、MC/FDV比率
- **交易数据**：24小时交易量、VOL/MC流动性比率
- **价格变化**：24小时涨跌幅统计
- **上线状态**：自动检测币安现货和合约上线情况
- **区块链分类**：按平台（Ethereum、Solana、Base等）智能分类

### AI智能投资建议

系统利用DeepSeek AI模型分析市场数据，提供：

- **市场趋势**：总体市场情绪和趋势分析
- **平台分析**：各区块链生态系统活跃度评估
- **项目推荐**：基于多维度数据的潜力项目识别
- **风险评估**：流动性、市值、价格波动等风险指标
- **投资策略**：短期、中期和长期投资建议
- **数据驱动**：所有建议基于实时市场数据

## 数据来源

- **币安Alpha项目数据**：CoinMarketCap API (`api.coinmarketcap.com`)
- **币安现货交易对**：Binance Spot API (`api.binance.com/api/v3/exchangeInfo`)
- **币安合约交易对**：Binance Futures API (`fapi.binance.com/fapi/v1/exchangeInfo`)
- **区块链平台分类**：基于项目标签与platform字段智能识别

## 目录结构

```
BinanceAlpha/
├── main.py                    # 主程序入口
├── webhook.py                 # WebHook消息推送
├── config.py                  # 配置文件
├── requirements.txt           # Python依赖
├── src/
│   ├── ai/                    # AI分析模块
│   │   └── alpha_advisor.py   # 投资建议生成器
│   ├── collectors/            # 数据收集模块
│   │   └── binance_alpha_collector.py
│   └── utils/                 # 工具模块
│       ├── binance_symbols.py # 币安交易对管理
│       ├── crypto_formatter.py# 数据格式化
│       ├── historical_data.py # 历史数据管理
│       └── image_generator.py # 图片生成工具
├── data/                      # 数据目录
│   └── platforms/             # 按平台分类的数据
├── advices/                   # AI建议报告
│   └── all-platforms/         # 汇总报告
├── images/                    # 生成的图片
├── symbols/                   # 交易对数据
│   ├── spot_symbols.json      # 现货交易对缓存
│   ├── futures_symbols.json   # 合约交易对缓存
│   └── raw/                   # 原始交易对数据
└── docs-viewer/               # Web文档查看器
    ├── src/                   # Vue.js源码
    ├── public/                # 静态资源
    └── dist/                  # 构建输出
```

## 注意事项

- 本系统仅提供市场数据分析参考，不构成投资建议
- 加密货币市场风险较大，请谨慎投资
- API访问可能受到速率限制，请合理控制请求频率
- 使用AI顾问功能需要有效的DeepSeek API密钥

## 许可证

MIT License
