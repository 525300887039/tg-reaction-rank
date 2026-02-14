# Telegram 频道表情统计分析工具

分析 Telegram 频道消息的表情反应数据，按目标表情（爱心、点赞等）数量排序，找出最受欢迎的消息。支持 Web 界面和命令行两种使用方式。

## 功能特性

- **频道列表浏览** — 连接 Telegram 账号，列出已加入的所有频道
- **表情统计分析** — 遍历频道全部消息，统计目标表情（❤️👍 等）反应数量
- **排行榜展示** — 按表情数量排序，生成可视化排行榜（Web 界面含消息配图）
- **关键词筛选** — 只显示包含指定关键词的消息
- **结果缓存** — 已分析过的频道直接使用缓存，支持强制重新分析
- **报告导出** — 下载为文本文件或一键发送到 Telegram 收藏夹
- **代理支持** — 支持 HTTP / SOCKS4 / SOCKS5 代理，可通过配置文件开关

## 截图

<!-- TODO: 添加截图 -->

## 前置条件

1. **Python >= 3.11**
2. **Telegram API 凭据** — 访问 [my.telegram.org/apps](https://my.telegram.org/apps) 创建应用，获取 `API_ID` 和 `API_HASH`
3. **网络代理**（可选） — 如果你所在的网络无法直连 Telegram，需要配置代理

## 安装

使用 [uv](https://github.com/astral-sh/uv)（推荐）：

```bash
uv sync
```

或使用 pip：

```bash
pip install telethon pysocks streamlit nest-asyncio
```

## 配置

1. 复制示例配置文件：

```bash
cp config.example.toml config.toml
```

2. 编辑 `config.toml`，填入你的真实值：

```toml
[telegram]
api_id = 12345678
api_hash = "your_api_hash_here"

[proxy]
enabled = true        # 不需要代理则设为 false
type = "HTTP"
host = "127.0.0.1"
port = 7890

[auth]
phone = "+861XXXXXXXXXX"
```

配置优先级：**环境变量 > config.toml > 默认值**。

## 使用方式

### Web 界面（推荐）

```bash
streamlit run streamlit_app.py
```

1. 首次使用前，先在命令行完成登录授权（见下方）
2. 点击侧边栏「连接 Telegram」
3. 从下拉列表选择频道
4. 点击「开始分析」（再次分析同一频道会自动使用缓存）
5. 可通过关键词筛选过滤结果
6. 勾选「忽略缓存」可强制重新获取数据

### 命令行 — 登录授权

首次运行需要完成手机号验证：

```bash
python telegram_channel_selector.py
```

按提示输入验证码即可，登录状态会保存到 session 文件中。

### 命令行 — 直接分析

在 `config.toml` 的 `[analyzer]` 中配置好频道和时间范围后：

```bash
python telegram_reaction_analyzer.py
```

## 环境变量

所有配置项均可通过环境变量覆盖，优先级高于 `config.toml`。

| 变量 | 说明 | 对应配置项 |
|------|------|-----------|
| `TELEGRAM_API_ID` | Telegram API ID | `telegram.api_id` |
| `TELEGRAM_API_HASH` | Telegram API Hash | `telegram.api_hash` |
| `TELEGRAM_PHONE` | 登录手机号 | `auth.phone` |
| `TELEGRAM_CODE` | 登录验证码 | `auth.code` |
| `TELEGRAM_PASSWORD` | 两步验证密码 | `auth.password` |
| `TELEGRAM_CHANNEL` | 目标频道用户名 | `analyzer.channel` |
| `START_DATE` | 分析起始时间 | `analyzer.start_date` |
| `END_DATE` | 分析结束时间 | `analyzer.end_date` |

## 项目结构

```
tg-reaction-rank/
├── pyproject.toml                   # 项目元数据与依赖声明
├── LICENSE                          # MIT 许可证
├── README.md
├── .gitignore
├── config.example.toml              # 配置文件示例（提交到 git）
├── config.toml                      # 真实配置（已 gitignore）
├── config_loader.py                 # 共享配置加载模块
├── streamlit_app.py                 # Streamlit Web 界面（主入口）
├── telegram_channel_selector.py     # 命令行版频道选择器 / 登录工具
├── telegram_reaction_analyzer.py    # 命令行版表情统计分析
├── .streamlit/
│   └── config.toml                  # Streamlit 主题配置
└── cache/                           # 分析结果缓存目录（自动生成）
    └── channel_{id}.json
```

## 技术栈

- [Telethon](https://github.com/LonamiWebs/Telethon) — Telegram MTProto API 客户端
- [Streamlit](https://streamlit.io/) — Web 界面框架
- [PySocks](https://github.com/Anorov/PySocks) — 代理支持
- [nest-asyncio](https://github.com/erdewit/nest_asyncio) — 嵌套事件循环支持
- Python 3.11+ 标准库 `tomllib` — TOML 配置解析
