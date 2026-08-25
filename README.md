# up366 作业答案与 U3ENC 工具

本仓库用于解析 up366 作业答案，以及处理 `.u3enc` 加密文件。

## 环境准备

```text
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## U3ENC 解密

从 exe 提取 AES 密钥：

```text
.\.venv\Scripts\python.exe u3enc_tool.py extract-key up366.exe
```

解密单个 `.u3enc` 文件：

```text
.\.venv\Scripts\python.exe u3enc_tool.py decrypt --exe up366.exe questionData.js.u3enc questionData.js
```

已知密钥时可直接解密：

```text
.\.venv\Scripts\python.exe u3enc_tool.py decrypt --key-hex {key-hex} questionData.js.u3enc questionData.js
```

算法说明：

- 算法：AES-128-CBC
- 密钥：从 `up366.exe` 内嵌引导代码中动态提取
- IV：文件前 16 字节
- 密文：文件第 17 字节起至结尾
- 填充：PKCS#7

## 提取作业答案

默认自动选取最新作业，输出到工作区 `最新作业答案.txt`：

```text
.\.venv\Scripts\python.exe extract_answers.py
```

指定某个作业（32 位 UUID）解析：

```text
.\.venv\Scripts\python.exe extract_answers.py --homework-uuid {uuid} --output answers/{uuid}.txt
```

只查看每题选项交换信息：

```text
.\.venv\Scripts\python.exe extract_option_order.py
```

注意：up366 的选项顺序保存在本机日志中，解析前需要先在 up366 中打开对应作业并进入答题页，让程序生成 `optionOrder`。

## 可视化页面

```text
.\.venv\Scripts\python.exe up366_answers_gui.py
```

功能：

- 默认数据目录 `D:\Up366StudentFiles`，右侧“选择目录”按钮可切换。
- 选定目录后自动保存到 `config/gui_config.json`，并刷新作业列表。
- 列表显示“作业UUID + 书本UUID + 修改时间”，默认选中最新作业。
- 首次启动需要定位 `up366.exe`，程序自动提取并保存 AES 密钥；之后解析不再需要 exe。
- 点“解析选中作业”生成 `./answers/<作业UUID>.txt`，随后用系统默认程序打开。

## 目录结构

```text
u3enc_tool.py            U3ENC 解密工具
extract_answers.py       作业答案提取 CLI
up366_answers_gui.py     可视化答案页面
```
