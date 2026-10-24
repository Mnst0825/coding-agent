# Web 开发经验

## Flask 应用
用 `app.test_client()` 写测试，不要真的启动服务器去请求。
模板放 templates/，静态文件放 static/，模板里用 `url_for('static', filename=...)` 引用。

## 前端页面与 HTML
关键词：网页、页面、前端、界面、html、css、javascript
写 HTML 页面时把 CSS 和 JS 内联在同一个文件里，方便直接用浏览器打开查看。
把用户输入或模型输出插入页面时用 textContent，不要用 innerHTML，防止 XSS。

## 调用 HTTP 接口
Python 里用 requests 或标准库 urllib.request，记得设置 timeout。
接口返回 JSON 时先检查状态码，再解析内容。
