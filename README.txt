Coding Agent —— 最小编程智能体
================================

基于 OpenAI 兼容接口的编程智能体，可以通过工具在工作区内读写文件、执行命令。
提供命令行和网页两种使用方式。

环境变量（写在 .env 中）
  MODEL            模型名称（必填）
  OPENAI_API_KEY   API Key
  OPENAI_BASE_URL  兼容接口地址，可选
  LLM_TIMEOUT      单次请求超时秒数，默认 60
  WEB_PASSWORD     网页登录密码（网页模式必填，不设置则无法登录）
  SECRET_KEY       Flask session 密钥（部署时务必设置，否则每次重启都要重新登录）

安装
  pip install -r requirements.txt

命令行
  python main.py                     交互模式
  python main.py "创建 hello.py 并运行"  单次任务
  python main.py --workspace ./ws --max-steps 50

网页
  python web.py                      本地启动，默认端口 8000
  Render 等平台使用 Procfile 启动（gunicorn）

工具
  read_file / write_file / edit_file / list_files / run_command
  所有路径限制在工作区内；网页模式下每个会话有独立的工作区。

知识库（RAG）
  knowledge/ 下的每个 .md 文件按 "## 标题" 切成条目。每次任务会用 BM25
  检索最相关的几条，附在任务后面交给模型参考，命中情况会打印 [RAG] 日志。
  新增经验：直接加一个 "## 标题" 段落即可，改完不用重启。
  检索靠关键词匹配，可以在条目里加一行 "关键词：..." 写上同义词提高命中率。
  RAG_DIR        知识库目录，默认 ./knowledge
  RAG_TOP_K      每次最多注入几条，默认 3
  RAG_MIN_SCORE  最低相关分数，默认 1.0，调高更严格

测试
  python -m unittest discover -s tests -t .

日志与 token 统计
  控制台：每次调用模型打印 [LLM] 输入/输出 tokens，任务结束打印 [统计] 汇总。
  logs/时间_任务.json   单个任务的完整记录：task、stats（tokens、步数、工具调用、
                        RAG 命中、耗时）、messages
  logs/usage.jsonl      每个任务一行统计，方便汇总，例如统计总消耗：
    python -c "import json;print(sum(json.loads(l)['total_tokens'] for l in open('logs/usage.jsonl',encoding='utf-8')))"
  部分兼容接口不返回用量，此时 tokens 记为 0，并在 usage_missing 中计数。
  网页端每条回答下方会显示本次的 tokens 和耗时，鼠标悬停可看知识库命中的条目。

安全提示
  run_command 可以执行任意 shell 命令，危险命令拦截只是简单的黑名单，
  不能当作沙箱。公开部署时请设置强密码，并尽量在容器等隔离环境中运行。


增加智能提示词的优化RAG库
对生成内容做一个评估，根据评估结果做一个再生成
后台做的事情做一个log，比如记录消耗多少tokens、匹配了哪些答案