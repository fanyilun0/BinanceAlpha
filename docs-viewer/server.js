import express from 'express'
import path from 'path'
import fs from 'fs'
import cors from 'cors'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const app = express()

// 允许所有来源的请求
app.use(cors())

// 静态文件服务
app.use(express.static(path.join(__dirname, 'dist')))

// 获取所有Markdown文件
app.get('/api/files', (req, res) => {
  const docsPath = path.join(__dirname, '../advices/all-platforms')
  fs.readdir(docsPath, (err, files) => {
    if (err) {
      console.error('Error reading directory:', err)
      return res.status(500).json({ error: '无法读取目录' })
    }
    
    const markdownFiles = files
      .filter(file => file.endsWith('.md'))
      .map(file => ({
        name: file,
        path: `/api/file/${file}`
      }))
    
    res.json(markdownFiles)
  })
})

// 获取单个文件内容
app.get('/api/file/:filename', (req, res) => {
  const filePath = path.join(__dirname, '../advices/all-platforms', req.params.filename)
  fs.readFile(filePath, 'utf8', (err, data) => {
    if (err) {
      console.error('Error reading file:', err)
      return res.status(500).json({ error: '无法读取文件' })
    }
    res.send(data)
  })
})

// 处理所有其他路由，返回index.html
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'dist', 'index.html'))
})

// 在生产环境中使用Vercel提供的端口
const PORT = process.env.PORT || 3000
app.listen(PORT, () => {
  console.log(`服务器运行在端口 ${PORT}`)
})

// 导出app供Vercel使用
export default app 