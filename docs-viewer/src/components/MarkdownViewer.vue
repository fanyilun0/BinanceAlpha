<template>
  <div class="markdown-viewer">
    <div class="markdown-content typora-style" v-html="renderedContent"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'

const props = defineProps({
  content: {
    type: String,
    required: true
  }
})

const renderedContent = ref('')

// 配置marked
marked.setOptions({
  gfm: true,
  breaks: true,
  headerIds: true,
  mangle: false,
  highlight: function(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value
    }
    return code
  }
})

const renderMarkdown = (content) => {
  try {
    renderedContent.value = marked.parse(content)
  } catch (error) {
    console.error('Markdown渲染错误:', error)
    renderedContent.value = '渲染错误'
  }
}

// 监听内容变化
watch(() => props.content, (newContent) => {
  renderMarkdown(newContent)
})

onMounted(() => {
  renderMarkdown(props.content)
})
</script>

<style>
.markdown-viewer {
  padding: 20px;
  max-width: 100%;
  overflow-x: auto;
}

.typora-style {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif;
  line-height: 1.6;
  color: #333;
  margin: 0 auto;
  padding: 20px;
}

/* 标题样式 */
.typora-style h1,
.typora-style h2,
.typora-style h3,
.typora-style h4,
.typora-style h5,
.typora-style h6 {
  margin: 1.2em 0 0.8em;
  padding: 0;
  font-weight: bold;
  text-align: left;
  color: #2c3e50;
}

.typora-style h1 {
  font-size: 2em;
  margin-top: 0;
  padding-bottom: 0.3em;
  border-bottom: 1px solid #eaecef;
}

.typora-style h2 {
  font-size: 1.5em;
  padding-bottom: 0.3em;
  border-bottom: 1px solid #eaecef;
}

.typora-style h3 {
  font-size: 1.25em;
}

.typora-style h4 {
  font-size: 1em;
}

/* 段落和列表样式 */
.typora-style p,
.typora-style ul,
.typora-style ol {
  margin: 0.8em 0;
  text-align: left;
}

.typora-style ul,
.typora-style ol {
  padding-left: 2em;
  margin: 0.5em 0;
}

.typora-style li {
  margin: 0.3em 0;
  text-align: left;
}

.typora-style li > p {
  margin: 0.2em 0;
}

/* 代码块样式 */
.typora-style code {
  background-color: rgba(27,31,35,0.05);
  padding: 0.2em 0.4em;
  border-radius: 3px;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 0.9em;
}

.typora-style pre {
  margin: 1em 0;
  padding: 1em;
  overflow: auto;
  background-color: #f6f8fa;
  border-radius: 3px;
  font-size: 0.9em;
}

.typora-style pre code {
  background: none;
  padding: 0;
  font-size: 1em;
}

/* 引用块样式 */
.typora-style blockquote {
  margin: 1em 0;
  padding: 0.5em 1em;
  color: #666;
  border-left: 4px solid #42b983;
  background-color: rgba(66, 185, 131, 0.1);
}

/* 表格样式 */
.typora-style table {
  border-collapse: collapse;
  margin: 1em 0;
  width: 100%;
  overflow: auto;
}

.typora-style table th,
.typora-style table td {
  border: 1px solid #dfe2e5;
  padding: 0.6em 1em;
  text-align: left;
}

.typora-style table th {
  background-color: #f6f8fa;
  font-weight: bold;
}

.typora-style table tr:nth-child(2n) {
  background-color: #f8f9fa;
}

/* 链接样式 */
.typora-style a {
  color: #42b983;
  text-decoration: none;
}

.typora-style a:hover {
  text-decoration: underline;
}

/* 图片样式 */
.typora-style img {
  max-width: 100%;
  margin: 1em 0;
}

/* 水平线样式 */
.typora-style hr {
  height: 1px;
  margin: 1.5em 0;
  border: none;
  background-color: #dfe2e5;
}

/* 行内元素样式 */
.typora-style strong {
  font-weight: 600;
}

.typora-style em {
  font-style: italic;
}

/* 代码高亮主题调整 */
.typora-style .hljs {
  background: #f6f8fa;
  color: #24292e;
  padding: 1em;
}
</style> 