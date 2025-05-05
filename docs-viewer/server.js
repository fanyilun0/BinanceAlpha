import express from 'express'
import path from 'path'
import fs from 'fs'
import cors from 'cors'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const app = express()

app.use(cors())
app.use(express.static('dist'))

// 获取所有Markdown文件
app.get('/api/files', (req, res) => {
  const docsPath = path.join(__dirname, '../advices/all-platforms')
  fs.readdir(docsPath, (err, files) => {
    if (err) {
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
      return res.status(500).json({ error: '无法读取文件' })
    }
    res.send(data)
  })
})

const PORT = 3000
app.listen(PORT, () => {
  console.log(`服务器运行在 http://localhost:${PORT}`)
}) 