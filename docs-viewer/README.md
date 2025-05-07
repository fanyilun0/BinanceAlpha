# Vue 3 + Vite

This template should help get you started developing with Vue 3 in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

Learn more about IDE Support for Vue in the [Vue Docs Scaling up Guide](https://vuejs.org/guide/scaling-up/tooling.html#ide-support).

# Markdown文档查看器

这是一个使用Vue 3和Vite构建的Markdown文档查看器，支持实时预览、搜索和暗黑模式。文档通过静态文件方式访问，无需服务器支持。

## 功能特点

- 📝 Markdown文档实时预览
- 🔍 文档搜索功能
- 🌓 暗黑模式支持
- 📱 响应式设计
- 🚀 静态文件访问，无需服务器

## 本地开发

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

开发服务器启动时会自动：
1. 生成文档列表（list.json）
2. 复制MD文件到public目录
3. 启动Vite开发服务器

## 部署到Vercel

### 1. 准备工作

1. 确保您有一个[Vercel账号](https://vercel.com/signup)
2. 安装Vercel CLI（可选）：
   ```bash
   npm install -g vercel
   ```

### 2. 项目配置

确保`package.json`中的构建脚本正确：
   ```json
   {
     "scripts": {
       "dev": "node scripts/generate-list.js && vite",
       "build": "node scripts/generate-list.js && vite build",
       "preview": "vite preview"
     }
   }
   ```

### 3. 部署步骤

#### 方法一：通过Vercel网站部署

1. 将代码推送到GitHub仓库
2. 登录[Vercel控制台](https://vercel.com/dashboard)
3. 点击"New Project"
4. 选择您的GitHub仓库
5. 在配置页面：
   - Framework Preset: 选择"Vue.js"
   - Build Command: `npm run build`
   - Output Directory: `dist`
   - Install Command: `npm install`
6. 点击"Deploy"

#### 方法二：通过Vercel CLI部署

1. 在项目根目录运行：
   ```bash
   vercel
   ```
2. 按照提示完成部署

## 项目结构

```
docs-viewer/
├── public/
│   └── advices/
│       └── all-platforms/
│           ├── list.json        # 自动生成的文档列表
│           └── *.md            # Markdown文档
├── src/
│   ├── components/            # Vue组件
│   ├── App.vue               # 主应用组件
│   └── main.js               # 应用入口
├── scripts/
│   └── generate-list.js      # 文档列表生成脚本
└── package.json              # 项目配置
```

## 文档管理

1. 文档位置：`advices/all-platforms/` 目录
2. 文档格式：`.md` 文件
3. 文档命名：建议使用 `advice_YYYYMMDD.md` 格式
4. 文档更新：添加新文档后，运行 `npm run generate-list` 更新列表

## 注意事项

1. 确保文档文件名格式正确
2. 文档内容使用标准Markdown格式
3. 建议在部署前测试生产构建：
   ```bash
   npm run build
   npm run preview
   ```

## 故障排除

1. 如果文档列表未更新：
   - 运行 `npm run generate-list` 手动更新
   - 检查文档目录权限

2. 如果文档无法加载：
   - 检查文档文件名是否正确
   - 确认文档已复制到public目录

3. 如果构建失败：
   - 检查Node.js版本
   - 确保所有依赖已安装

## 技术支持

如有问题，请提交Issue或联系维护者。
