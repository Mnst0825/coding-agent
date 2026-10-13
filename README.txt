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

测试
  python -m unittest discover -s tests -t .

安全提示
  run_command 可以执行任意 shell 命令，危险命令拦截只是简单的黑名单，
  不能当作沙箱。公开部署时请设置强密码，并尽量在容器等隔离环境中运行。
