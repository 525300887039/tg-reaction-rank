# Telegram 频道表情统计分析工具

分析 Telegram 频道消息的表情反应数据，按目标表情（爱心、点赞等）数量排序，找出最受欢迎的消息。支持 Web 界面、Telegram Bot 和命令行三种使用方式。

## 功能特性

- **频道列表浏览** — 连接 Telegram 账号，列出已加入的所有频道
- **表情统计分析** — 遍历频道全部消息，统计目标表情（❤️👍 等）反应数量
- **排行榜展示** — 按表情数量排序，生成可视化排行榜（Web 界面含消息配图）
- **自定义目标表情** — 在侧边栏自由选择要统计的表情，支持实时切换
- **关键词筛选** — 只显示包含指定关键词的消息
- **结果缓存** — 已分析过的频道直接使用缓存，支持强制重新分析
- **Bot 交互** — 向 Telegram Bot 转发频道消息、发送频道链接或用户名，即可获取该频道 Reaction 排行 Top 50
- **报告导出** — 下载为文本文件或一键发送到 Telegram 收藏夹
- **代理支持** — 支持 HTTP / SOCKS4 / SOCKS5 代理，可通过配置文件开关

## 截图

<!-- TODO: 添加截图 -->

## 前置条件

1. **Python 3.14**
2. **Telegram API 凭据** — 访问 [my.telegram.org/apps](https://my.telegram.org/apps) 创建应用，获取 `API_ID` 和 `API_HASH`
3. **网络代理**（可选） — 如果你所在的网络无法直连 Telegram，需要配置代理

## 安装

使用 [uv](https://github.com/astral-sh/uv)（推荐）：

```bash
uv sync
```

或使用 pip：

```bash
pip install telethon pysocks streamlit
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
bot_token = ""              # 从 @BotFather 获取，用于 Bot 模式

[proxy]
enabled = true        # 不需要代理则设为 false
type = "HTTP"
host = "127.0.0.1"
port = 7890

[auth]
phone = "+861XXXXXXXXXX"

[analyzer]
channel = "your_channel_username"
# target_emojis = ["❤️", "👍", "🔥"]  # 自定义目标表情（留空使用默认列表）
```

配置优先级：**环境变量 > config.toml > 默认值**。

## 使用方式

### Web 界面（推荐）

```bash
uv run streamlit run streamlit_app.py
```

1. 首次使用前，先在命令行完成登录授权（见下方）
2. 启动后自动连接 Telegram（失败时可点击「重试连接」）
3. 从下拉列表选择频道
4. 点击「开始分析」（再次分析同一频道会自动使用缓存）
5. 可在侧边栏自定义目标表情、通过关键词筛选过滤结果
6. 勾选「忽略缓存」可强制重新获取数据

### 命令行 — 登录授权

首次运行需要完成手机号验证：

```bash
uv run python telegram_channel_selector.py
```

按提示输入验证码即可，登录状态会保存到 session 文件中。

### Telegram Bot

1. 从 [@BotFather](https://t.me/BotFather) 创建 Bot 并获取 token
2. 在 `config.toml` 的 `[telegram]` 段填入 `bot_token`
3. 启动 Bot：

```bash
uv run python telegram_bot.py
```

4. 在 Telegram 中向 Bot 发送频道链接（如 `https://t.me/channel_name`）、用户名（如 `@channel_name`）或转发频道中的任意消息，即可收到该频道 Reaction 排行 Top 50

> Bot 仅作为交互前端，实际数据通过已登录的用户客户端获取，因此需要先完成登录授权。

### 命令行 — 直接分析

在 `config.toml` 的 `[analyzer]` 中配置好频道和时间范围后：

```bash
uv run python telegram_reaction_analyzer.py
```

## 环境变量

所有配置项均可通过环境变量覆盖，优先级高于 `config.toml`。

| 变量 | 说明 | 对应配置项 |
|------|------|-----------|
| `TELEGRAM_API_ID` | Telegram API ID | `telegram.api_id` |
| `TELEGRAM_API_HASH` | Telegram API Hash | `telegram.api_hash` |
| `TELEGRAM_BOT_TOKEN` | Bot Token（@BotFather） | `telegram.bot_token` |
| `TELEGRAM_PHONE` | 登录手机号 | `auth.phone` |
| `TELEGRAM_CODE` | 登录验证码 | `auth.code` |
| `TELEGRAM_PASSWORD` | 两步验证密码 | `auth.password` |
| `TELEGRAM_CHANNEL` | 目标频道用户名 | `analyzer.channel` |
| `START_DATE` | 分析起始时间 | `analyzer.start_date` |
| `END_DATE` | 分析结束时间 | `analyzer.end_date` |
| `TARGET_EMOJIS` | 目标表情（逗号分隔） | `analyzer.target_emojis` |

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
├── analyzer_core.py                 # 核心分析逻辑（多入口复用）
├── streamlit_app.py                 # Streamlit Web 界面（主入口）
├── telegram_bot.py                  # Telegram Bot 入口
├── telegram_channel_selector.py     # 命令行版频道选择器 / 登录工具
├── telegram_reaction_analyzer.py    # 命令行版表情统计分析
├── .streamlit/
│   └── config.toml                  # Streamlit 主题配置
└── cache/                           # 缓存目录（自动生成）
    ├── channel_{id}.json            # 分析结果缓存
    ├── raw_{id}.json                # 原始数据缓存
    └── images/{id}/                 # 消息配图缓存
```

## 技术栈

- [Telethon](https://github.com/LonamiWebs/Telethon) — Telegram MTProto API 客户端
- [Streamlit](https://streamlit.io/) — Web 界面框架
- [PySocks](https://github.com/Anorov/PySocks) — 代理支持
- Python 3.14 标准库 `tomllib` — TOML 配置解析
