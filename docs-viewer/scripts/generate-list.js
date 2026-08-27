import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

// 获取当前文件的目录路径
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 源目录和目标目录
const advicesSourceDir = path.join(__dirname, '../../advices/all-platforms');
const imagesSourceDir = path.join(__dirname, '../../images');
const tablesSourceDir = path.join(__dirname, '../../data');
const chartsSourceDir = path.join(__dirname, '../public/charts');
const futuresSymbolsSource = path.join(__dirname, '../../symbols/futures_symbols.json');
const advicesTargetDir = path.join(__dirname, '../public/advices');
const imagesTargetDir = path.join(__dirname, '../public/images');
const tablesTargetDir = path.join(__dirname, '../public/tables');
const chartsTargetDir = path.join(__dirname, '../public/charts');
const futuresSymbolsTarget = path.join(__dirname, '../public/futures_symbols.json');

// 数据保留天数限制（与 Python 侧 DATA_RETENTION 保持一致）
const RETENTION_DAYS = {
  images: 30,
  tables: 30,
  advices: 90,
};

function isWithinRetention(filename, retentionDays) {
  const dateMatch = filename.match(/(\d{8})/);
  if (!dateMatch) return true;
  const fileDate = new Date(
    dateMatch[1].slice(0, 4),
    parseInt(dateMatch[1].slice(4, 6)) - 1,
    dateMatch[1].slice(6, 8)
  );
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - retentionDays);
  return fileDate >= cutoff;
}

// 确保目标目录存在
if (!fs.existsSync(advicesTargetDir)) {
  fs.mkdirSync(advicesTargetDir, { recursive: true });
}
if (!fs.existsSync(imagesTargetDir)) {
  fs.mkdirSync(imagesTargetDir, { recursive: true });
}
if (!fs.existsSync(tablesTargetDir)) {
  fs.mkdirSync(tablesTargetDir, { recursive: true });
}
if (!fs.existsSync(chartsTargetDir)) {
  fs.mkdirSync(chartsTargetDir, { recursive: true });
}

// 生成图表数据
console.log('🔄 开始生成图表数据...');
try {
  execSync('node scripts/generate-volume-chart-data.js', { 
    cwd: path.join(__dirname, '..'),
    stdio: 'inherit' 
  });
  console.log('✅ 图表数据生成完成');
} catch (error) {
  console.error('❌ 图表数据生成失败:', error.message);
}

// 读取源目录中的所有 .md 文件（仅保留期限内）
let mdFiles = [];
if (fs.existsSync(advicesSourceDir)) {
  mdFiles = fs.readdirSync(advicesSourceDir)
    .filter(file => file.endsWith('.md') && isWithinRetention(file, RETENTION_DAYS.advices))
    .map(file => ({
      name: file,
      title: file.replace('.md', '').replace(/_/g, ' ')
    }))
    .sort((a, b) => b.name.localeCompare(a.name));
} else {
  console.log(`⚠️  文档目录不存在: ${advicesSourceDir}`);
}

// 读取图片目录中的 .png 文件（仅保留期限内），并按类型分类
let imageFiles = [];
if (fs.existsSync(imagesSourceDir)) {
  imageFiles = fs.readdirSync(imagesSourceDir)
    .filter(file => file.endsWith('.png') && isWithinRetention(file, RETENTION_DAYS.images))
    .map(file => {
      // 根据文件名确定图片类型
      let type = 'other';
      if (file.includes('alpha_list_')) {
        type = 'alpha_list';
      } else if (file.includes('top_vol_mc_ratio_')) {
        type = 'vol_mc_ratio';
      } else if (file.includes('gainers_losers_')) {
        type = 'gainers_losers';
      }
      
      return {
        name: file,
        title: file.replace('.png', '').replace(/_/g, ' '),
        // 提取日期信息（假设文件名格式为 alpha_list_20250930083006.png）
        date: file.match(/\d{8}/)?.[0] || '',
        type: type  // 新增类型字段
      };
    })
    .sort((a, b) => b.name.localeCompare(a.name)); // 按文件名降序排序
} else {
  console.log(`⚠️  图片资源目录不存在: ${imagesSourceDir}`);
}

// 读取表格数据目录中的 .json 文件（仅保留期限内），并按类型分类
let tableFiles = [];
if (fs.existsSync(tablesSourceDir)) {
  tableFiles = fs.readdirSync(tablesSourceDir)
    .filter(file => {
      return (file.startsWith('filtered_crypto_list_') || file.startsWith('trend_signals_'))
        && file.endsWith('.json')
        && isWithinRetention(file, RETENTION_DAYS.tables);
    })
    .map(file => {
      // 确定表格类型
      let type = 'other';
      if (file.startsWith('filtered_crypto_list_')) {
        type = 'crypto_list';
      } else if (file.startsWith('trend_signals_')) {
        type = 'trend_signals';
      }
      
      return {
        name: file,
        title: file.replace('.json', '').replace(/_/g, ' '),
        // 提取日期信息（假设文件名格式为 filtered_crypto_list_20250426.json 或 trend_signals_20251210.json）
        date: file.match(/\d{8}/)?.[0] || '',
        type: type  // 新增类型字段
      };
    })
    .sort((a, b) => b.name.localeCompare(a.name)); // 按文件名降序排序
} else {
  console.log(`⚠️  表格数据目录不存在: ${tablesSourceDir}`);
}

// 读取图表数据目录中的所有 .json 文件
let chartFiles = [];
if (fs.existsSync(chartsSourceDir)) {
  chartFiles = fs.readdirSync(chartsSourceDir)
    .filter(file => file.endsWith('.json'))
    .map(file => {
      return {
        name: file,
        title: file.replace('.json', '').replace(/_/g, ' '),
      };
    })
    .sort((a, b) => b.name.localeCompare(a.name)); // 按文件名降序排序
} else {
  console.log(`⚠️  图表数据目录不存在: ${chartsSourceDir}`);
}

// 生成 list.json，包含文档、图片、表格和图表列表
const listJson = {
  files: mdFiles,
  images: imageFiles,
  tables: tableFiles,
  charts: chartFiles
};

console.log('文档数量:', mdFiles.length);
console.log('图片数量:', imageFiles.length);
console.log('表格数量:', tableFiles.length);
console.log('图表数量:', chartFiles.length);

// 写入 list.json
fs.writeFileSync(
  path.join(advicesTargetDir, 'list.json'),
  JSON.stringify(listJson, null, 2)
);

// 复制所有 .md 文件到目标目录
if (mdFiles.length > 0) {
  mdFiles.forEach(file => {
    const sourceFile = path.join(advicesSourceDir, file.name);
    const targetFile = path.join(advicesTargetDir, file.name);
    fs.copyFileSync(sourceFile, targetFile);
  });
}

// 复制所有 .png 文件到目标目录（仅当源目录存在时）
if (imageFiles.length > 0 && fs.existsSync(imagesSourceDir)) {
  imageFiles.forEach(file => {
    const sourceFile = path.join(imagesSourceDir, file.name);
    const targetFile = path.join(imagesTargetDir, file.name);
    fs.copyFileSync(sourceFile, targetFile);
  });
}

// 复制所有表格数据 .json 文件到目标目录（仅当源目录存在时）
if (tableFiles.length > 0 && fs.existsSync(tablesSourceDir)) {
  tableFiles.forEach(file => {
    const sourceFile = path.join(tablesSourceDir, file.name);
    const targetFile = path.join(tablesTargetDir, file.name);
    fs.copyFileSync(sourceFile, targetFile);
  });
}

// 复制 futures_symbols.json 文件到 public 目录
if (fs.existsSync(futuresSymbolsSource)) {
  fs.copyFileSync(futuresSymbolsSource, futuresSymbolsTarget);
  console.log('✅ futures_symbols.json 已复制到 public 目录');
} else {
  console.log('⚠️  futures_symbols.json 文件不存在，跳过复制');
}

console.log('✅ list.json 生成完成');
console.log(`✅ MD 文件已复制到 public/advices 目录 (${mdFiles.length} 个文件)`);
if (imageFiles.length > 0 && fs.existsSync(imagesSourceDir)) {
  console.log(`✅ 图片文件已复制到 public/images 目录 (${imageFiles.length} 个文件)`);
} else if (!fs.existsSync(imagesSourceDir)) {
  console.log('ℹ️  图片目录不存在，跳过图片复制（这在 Vercel 构建环境中是正常的）');
} else {
  console.log('ℹ️  没有图片文件需要复制');
}
if (tableFiles.length > 0 && fs.existsSync(tablesSourceDir)) {
  console.log(`✅ 表格数据已复制到 public/tables 目录 (${tableFiles.length} 个文件)`);
} else if (!fs.existsSync(tablesSourceDir)) {
  console.log('ℹ️  表格数据目录不存在，跳过表格数据复制');
} else {
  console.log('ℹ️  没有表格数据需要复制');
} 