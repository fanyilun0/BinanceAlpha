import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import './App.css'

function App() {
  const [files, setFiles] = useState([])
  const [currentFile, setCurrentFile] = useState(null)
  const [content, setContent] = useState('')

  useEffect(() => {
    // 获取文件列表
    fetch('/advices/list.json')
      .then(res => res.json())
      .then(data => setFiles(data.files))
      .catch(err => console.error('Error loading file list:', err))
  }, [])

  useEffect(() => {
    if (currentFile) {
      // 获取当前选中的文件内容
      fetch(`/advices/${currentFile.name}`)
        .then(res => res.text())
        .then(text => setContent(text))
        .catch(err => console.error('Error loading file:', err))
    }
  }, [currentFile])

  return (
    <div className="app">
      <div className="sidebar">
        <h2>文档列表</h2>
        <ul>
          {files.map(file => (
            <li 
              key={file.name}
              className={currentFile?.name === file.name ? 'active' : ''}
              onClick={() => setCurrentFile(file)}
            >
              {file.title}
            </li>
          ))}
        </ul>
      </div>
      <div className="content">
        {content ? (
          <ReactMarkdown>{content}</ReactMarkdown>
        ) : (
          <p>请从左侧选择文档</p>
        )}
      </div>
    </div>
  )
}

export default App 