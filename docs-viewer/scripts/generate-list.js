import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// 获取当前文件的目录路径
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 源目录和目标目录
const advicesSourceDir = path.join(__dirname, '../../advices/all-platforms');
const imagesSourceDir = path.join(__dirname, '../../data/images');
const advicesTargetDir = path.join(__dirname, '../public/advices');
const imagesTargetDir = path.join(__dirname, '../public/images');

// 确保目标目录存在
if (!fs.existsSync(advicesTargetDir)) {
  fs.mkdirSync(advicesTargetDir, { recursive: true });
}
if (!fs.existsSync(imagesTargetDir)) {
  fs.mkdirSync(imagesTargetDir, { recursive: true });
}

// 读取源目录中的所有 .md 文件
const mdFiles = fs.readdirSync(advicesSourceDir)
  .filter(file => file.endsWith('.md'))
  .map(file => ({
    name: file,
    title: file.replace('.md', '').replace(/_/g, ' ')
  }))
  .sort((a, b) => b.name.localeCompare(a.name)); // 按文件名降序排序

// 读取图片目录中的所有 .png 文件
const imageFiles = fs.readdirSync(imagesSourceDir)
  .filter(file => file.endsWith('.png'))
  .map(file => ({
    name: file,
    title: file.replace('.png', '').replace(/_/g, ' '),
    // 提取日期信息（假设文件名格式为 alpha_list_20250930083006.png）
    date: file.match(/\d{8}/)?.[0] || ''
  }))
  .sort((a, b) => b.name.localeCompare(a.name)); // 按文件名降序排序

// 生成 list.json，包含文档和图片列表
const listJson = {
  files: mdFiles,
  images: imageFiles
};

console.log('文档数量:', mdFiles.length);
console.log('图片数量:', imageFiles.length);

// 写入 list.json
fs.writeFileSync(
  path.join(advicesTargetDir, 'list.json'),
  JSON.stringify(listJson, null, 2)
);

// 复制所有 .md 文件到目标目录
mdFiles.forEach(file => {
  const sourceFile = path.join(advicesSourceDir, file.name);
  const targetFile = path.join(advicesTargetDir, file.name);
  fs.copyFileSync(sourceFile, targetFile);
});

// 复制所有 .png 文件到目标目录
imageFiles.forEach(file => {
  const sourceFile = path.join(imagesSourceDir, file.name);
  const targetFile = path.join(imagesTargetDir, file.name);
  fs.copyFileSync(sourceFile, targetFile);
});

console.log('✅ list.json 生成完成');
console.log('✅ MD 文件已复制到 public/advices 目录');
console.log('✅ 图片文件已复制到 public/images 目录'); 