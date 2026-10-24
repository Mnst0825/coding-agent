# Python 开发经验

## 运行 Python 测试
优先用标准库 unittest：`python -m unittest discover -s tests -t .`。
如果项目里有 pytest.ini、pyproject.toml 中的 [tool.pytest] 或 conftest.py，说明用的是 pytest，改用 `python -m pytest -q`。
测试失败时先读完整的报错栈，定位到具体文件和行号再修改。

## 安装 Python 依赖
用 `python -m pip install -r requirements.txt`，不要直接用 pip，避免装到别的解释器里。
新增依赖后记得同步写进 requirements.txt。

## Python 文件编码与中文输出
读写文件时显式指定 `encoding="utf-8"`。
Windows 控制台打印中文乱码时，可以在命令前加 `set PYTHONIOENCODING=utf-8 &&`。

## 创建 Python 脚本并运行
新建脚本用 write_file，写完立即用 `python 文件名.py` 运行验证，确认输出符合预期再总结。
脚本需要命令行参数时用 argparse，并给出 --help 说明。
