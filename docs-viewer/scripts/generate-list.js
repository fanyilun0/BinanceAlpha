import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// 获取当前文件的目录路径
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 源目录和目标目录
const sourceDir = path.join(__dirname, '../../advices/all-platforms');
const targetDir = path.join(__dirname, '../public/advices');

// 确保目标目录存在
if (!fs.existsSync(targetDir)) {
  fs.mkdirSync(targetDir, { recursive: true });
}

// 读取源目录中的所有 .md 文件
const files = fs.readdirSync(sourceDir)
  .filter(file => file.endsWith('.md'))
  .map(file => ({
    name: file,
    title: file.replace('.md', '').replace(/_/g, ' ')
  }))
  .sort((a, b) => b.name.localeCompare(a.name)); // 按文件名降序排序

// 生成 list.json
const listJson = {
  files: files
};

console.log(listJson);

// 写入 list.json
fs.writeFileSync(
  path.join(targetDir, 'list.json'),
  JSON.stringify(listJson, null, 2)
);

// 复制所有 .md 文件到目标目录
files.forEach(file => {
  const sourceFile = path.join(sourceDir, file.name);
  const targetFile = path.join(targetDir, file.name);
  fs.copyFileSync(sourceFile, targetFile);
});

console.log('✅ list.json 生成完成，MD 文件已复制到 public 目录'); 