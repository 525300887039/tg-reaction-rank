"""config_loader 模块测试。"""

import os
from unittest import mock

from config_loader import TARGET_EMOJIS, load_config


def test_target_emojis_is_nonempty_list():
    """TARGET_EMOJIS 应为非空字符串列表。"""
    assert isinstance(TARGET_EMOJIS, list)
    assert len(TARGET_EMOJIS) > 0
    assert all(isinstance(e, str) for e in TARGET_EMOJIS)


def test_target_emojis_contains_expected():
    """TARGET_EMOJIS 应包含常见的爱心和点赞表情。"""
    assert '👍' in TARGET_EMOJIS
    assert '🔥' in TARGET_EMOJIS


def test_load_config_returns_expected_keys():
    """load_config() 应返回包含所有预期键的字典。"""
    cfg = load_config()
    expected_keys = {
        'api_id', 'api_hash', 'session_name', 'proxy',
        'phone', 'code', 'password', 'channel',
        'start_date', 'end_date',
    }
    assert set(cfg.keys()) == expected_keys


def test_load_config_session_name_is_absolute():
    """session_name 应被解析为绝对路径。"""
    cfg = load_config()
    assert os.path.isabs(cfg['session_name'])


def test_load_config_env_override():
    """环境变量应覆盖 TOML 配置值。"""
    with mock.patch.dict(os.environ, {'TELEGRAM_PHONE': '+1234567890'}):
        cfg = load_config()
        assert cfg['phone'] == '+1234567890'
