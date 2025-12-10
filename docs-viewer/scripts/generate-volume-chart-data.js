import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// 获取当前文件的目录路径
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 数据目录路径
const DATA_DIR = path.join(__dirname, '../../data');
const OUTPUT_DIR = path.join(__dirname, '../public/charts');

// 确保输出目录存在
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

/**
 * 从文件名中提取日期
 * @param {string} filename - 文件名，支持两种格式：
 *   - "filtered_crypto_list_20251202083022.json" (带时间戳)
 *   - "filtered_crypto_list_20251202.json" (仅日期)
 * @returns {string|null} - 日期字符串，例如 "2025-12-02"
 */
function extractDateFromFilename(filename) {
  // 匹配两种格式：YYYYMMDD 或 YYYYMMDDHHMMSS
  const match = filename.match(/filtered_crypto_list_(\d{8})(?:\d{6})?\.json/);
  if (match) {
    const dateStr = match[1];
    const year = dateStr.substring(0, 4);
    const month = dateStr.substring(4, 6);
    const day = dateStr.substring(6, 8);
    return `${year}-${month}-${day}`;
  }
  return null;
}

/**
 * 从JSON数据中提取所有token的交易量数据
 * @param {Array} data - JSON数据数组
 * @returns {Array} - 包含 {symbol, name, volume24h, platform} 的数组
 */
function getAllTokensWithVolume(data) {
  if (!Array.isArray(data)) {
    return [];
  }

  const tokensWithVolume = data
    .map(item => {
      const usdQuote = item.quotes?.find(q => q.name === 'USD');
      const volume24h = usdQuote?.volume24h || 0;
      const platform = item.platform?.symbol || item.platform?.name || 'Unknown';
      return {
        symbol: item.symbol || '',
        name: item.name || '',
        volume24h: volume24h,
        platform: platform
      };
    })
    .filter(item => item.symbol); // 只要求有symbol，允许volume为0

  return tokensWithVolume;
}

/**
 * 处理所有历史数据文件
 */
function processHistoricalData() {
  console.log('开始处理历史数据...');

  // 获取所有 filtered_crypto_list 文件
  const files = fs.readdirSync(DATA_DIR)
    .filter(file => file.startsWith('filtered_crypto_list_') && file.endsWith('.json'))
    .sort(); // 按文件名排序

  console.log(`找到 ${files.length} 个数据文件`);

  // 存储每个日期的数据
  const dateDataMap = new Map();

  // 处理每个文件
  for (const file of files) {
    const date = extractDateFromFilename(file);
    if (!date) {
      console.log(`跳过文件（无法提取日期）: ${file}`);
      continue;
    }

    const filePath = path.join(DATA_DIR, file);
    try {
      const content = fs.readFileSync(filePath, 'utf8');
      const data = JSON.parse(content);
      const allTokens = getAllTokensWithVolume(data);

      dateDataMap.set(date, allTokens);
      console.log(`处理完成: ${date} - 找到 ${allTokens.length} 个token`);
    } catch (error) {
      console.error(`处理文件失败 ${file}:`, error.message);
    }
  }

  // 按日期排序
  const sortedDates = Array.from(dateDataMap.keys()).sort();
  console.log(`\n总共处理了 ${sortedDates.length} 天的数据`);

  // 收集所有出现过的token及其平台信息
  const allTokensMap = new Map(); // symbol -> {name, platforms: Set}
  for (const tokens of dateDataMap.values()) {
    tokens.forEach(token => {
      if (!allTokensMap.has(token.symbol)) {
        allTokensMap.set(token.symbol, {
          name: token.name,
          platforms: new Set()
        });
      }
      allTokensMap.get(token.symbol).platforms.add(token.platform);
    });
  }
  const allTokens = Array.from(allTokensMap.keys()).sort();
  console.log(`总共有 ${allTokens.length} 个不同的token`);

  // 构建时间序列数据
  // 格式: { dates: [], tokens: { 'BTC': { volumes: [100, 200, ...], name: 'Bitcoin', platforms: ['ETH', 'BNB'] } } }
  const timeSeriesData = {
    dates: sortedDates,
    tokens: {}
  };

  // 为每个token构建时间序列
  for (const token of allTokens) {
    const volumeSeries = [];
    for (const date of sortedDates) {
      const dayData = dateDataMap.get(date) || [];
      const tokenData = dayData.find(t => t.symbol === token);
      // 将交易量转换为百万美元单位
      const volumeInMillions = tokenData ? tokenData.volume24h / 1000000 : null;
      volumeSeries.push(volumeInMillions);
    }
    const tokenInfo = allTokensMap.get(token);
    timeSeriesData.tokens[token] = {
      volumes: volumeSeries,
      name: tokenInfo.name,
      platforms: Array.from(tokenInfo.platforms).sort()
    };
  }

  // 保存数据
  const outputPath = path.join(OUTPUT_DIR, 'volume_time_series.json');
  fs.writeFileSync(outputPath, JSON.stringify(timeSeriesData, null, 2));
  console.log(`\n图表数据已保存到: ${outputPath}`);

  return timeSeriesData;
}

/**
 * 获取出现次数最多的token
 */
function getTopTokensByAppearance(tokensData, topN = 30) {
  const tokenAppearance = [];

  for (const [token, data] of Object.entries(tokensData)) {
    const volumes = data.volumes || data; // 兼容新旧格式
    const count = volumes.filter(v => v !== null && v > 0).length;
    tokenAppearance.push({ token, count });
  }

  return tokenAppearance.sort((a, b) => b.count - a.count).slice(0, topN);
}

// 执行处理
try {
  processHistoricalData();
  console.log('\n✅ 数据处理完成！');
} catch (error) {
  console.error('❌ 处理失败:', error);
  process.exit(1);
}

