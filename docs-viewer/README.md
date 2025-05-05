# Vue 3 + Vite

This template should help get you started developing with Vue 3 in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

Learn more about IDE Support for Vue in the [Vue Docs Scaling up Guide](https://vuejs.org/guide/scaling-up/tooling.html#ide-support).

# Markdown文档查看器

这是一个使用Vue 3和Vite构建的Markdown文档查看器，支持实时预览、搜索和暗黑模式。

## 本地开发

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run start
```

## 部署到Vercel

### 1. 准备工作

1. 确保您有一个[Vercel账号](https://vercel.com/signup)
2. 安装Vercel CLI（可选）：
   ```bash
   npm install -g vercel
   ```

### 2. 项目配置

1. 创建`vercel.json`配置文件：
   ```json
   {
     "version": 2,
     "builds": [
       {
         "src": "server.js",
         "use": "@vercel/node"
       },
       {
         "src": "package.json",
         "use": "@vercel/static-build",
         "config": {
           "distDir": "dist"
         }
       }
     ],
     "routes": [
       {
         "src": "/api/(.*)",
         "dest": "server.js"
       },
       {
         "src": "/(.*)",
         "dest": "/$1"
       }
     ]
   }
   ```

2. 更新`package.json`中的构建脚本：
   ```json
   {
     "scripts": {
       "build": "vite build",
       "start": "node server.js"
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

### 4. 环境变量配置

在Vercel项目设置中添加以下环境变量（如果需要）：

- `NODE_ENV`: `production`

### 5. 自定义域名（可选）

1. 在Vercel项目设置中点击"Domains"
2. 添加您的自定义域名
3. 按照提示配置DNS记录

## 注意事项

1. 确保`server.js`中的文件路径正确，可能需要根据Vercel的环境调整
2. 如果遇到CORS问题，确保在`server.js`中正确配置了CORS
3. 建议在部署前测试生产构建：
   ```bash
   npm run build
   npm run preview
   ```

## 故障排除

1. 如果部署后无法访问API：
   - 检查`vercel.json`中的路由配置
   - 确保`server.js`中的路径正确

2. 如果静态资源无法加载：
   - 检查构建输出目录是否正确
   - 确保`vercel.json`中的路由配置正确

3. 如果遇到权限问题：
   - 检查文件读取权限
   - 确保环境变量配置正确

## 技术支持

如有问题，请提交Issue或联系维护者。
