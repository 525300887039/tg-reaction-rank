"""
共享配置加载模块。

从 TOML 配置文件和环境变量中读取项目所需的全部配置项，
供其他脚本通过 ``from config_loader import load_config`` 统一调用。

优先级：环境变量 > config.toml > 默认值
"""

import os
import tomllib
from typing import TypedDict

TARGET_EMOJIS: list[str] = [
    '❤️', '👍', '🤍', '💜', '💙', '💚', '💛', '🧡', '🖤', '🤎',
    '❤', '♥', '💕', '💞', '💓', '💗', '💖', '💘', '💝', '👍🏻',
    '👍🏼', '👍🏽', '👍🏾', '👍🏿', '🙏', '🔥', '💯', '❣️', '♥️'
]


class TelegramConfig(TypedDict):
    api_id: int | None
    api_hash: str | None
    session_name: str
    proxy: tuple | None
    phone: str
    code: str
    password: str
    channel: str
    start_date: str
    end_date: str


_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_CONFIG_DIR, 'config.toml')


def load_config() -> TelegramConfig:
    """
    加载并合并全部配置项。

    从 ``config.toml`` 读取基础配置，再用同名环境变量覆盖。
    若 TOML 文件不存在则静默回退到环境变量与默认值。

    返回
    ----
    dict
        包含以下键的字典：

        - ``api_id`` : int 或 None
        - ``api_hash`` : str 或 None
        - ``session_name`` : str — 绝对路径
        - ``proxy`` : tuple 或 None — Telethon 代理三元组
        - ``phone`` : str
        - ``code`` : str
        - ``password`` : str
        - ``channel`` : str
        - ``start_date`` : str
        - ``end_date`` : str
    """
    # 读取 TOML 文件（不存在则用空字典）
    toml_cfg = {}
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, 'rb') as f:
            toml_cfg = tomllib.load(f)

    tg = toml_cfg.get('telegram', {})
    proxy_cfg = toml_cfg.get('proxy', {})
    auth = toml_cfg.get('auth', {})
    analyzer = toml_cfg.get('analyzer', {})

    # --- telegram ---
    api_id_raw = os.getenv('TELEGRAM_API_ID') or tg.get('api_id')
    api_id = int(api_id_raw) if api_id_raw is not None else None

    api_hash = os.getenv('TELEGRAM_API_HASH') or tg.get('api_hash')

    session_rel = tg.get('session_name', 'telegram_session')
    session_name = os.path.normpath(os.path.join(_CONFIG_DIR, session_rel))

    # --- proxy ---
    proxy = None
    if proxy_cfg.get('enabled', False):
        proxy_type_str = proxy_cfg.get('type', 'HTTP').upper()
        # 延迟导入 socks，仅在启用代理时需要
        import socks
        type_map = {
            'HTTP': socks.HTTP,
            'SOCKS4': socks.SOCKS4,
            'SOCKS5': socks.SOCKS5,
        }
        proxy = (
            type_map.get(proxy_type_str, socks.HTTP),
            proxy_cfg.get('host', '127.0.0.1'),
            proxy_cfg.get('port', 7890),
        )

    # --- auth ---
    phone = os.getenv('TELEGRAM_PHONE') or auth.get('phone', '')
    code = os.getenv('TELEGRAM_CODE') or auth.get('code', '')
    password = os.getenv('TELEGRAM_PASSWORD') or auth.get('password', '')

    # --- analyzer ---
    channel = os.getenv('TELEGRAM_CHANNEL') or analyzer.get('channel', '')
    start_date = os.getenv('START_DATE') or analyzer.get('start_date', '')
    end_date = os.getenv('END_DATE') or analyzer.get('end_date', '')

    return {
        'api_id': api_id,
        'api_hash': api_hash,
        'session_name': session_name,
        'proxy': proxy,
        'phone': phone,
        'code': code,
        'password': password,
        'channel': channel,
        'start_date': start_date,
        'end_date': end_date,
    }
