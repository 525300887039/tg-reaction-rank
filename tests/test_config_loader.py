"""config_loader 模块测试。"""

import os
from unittest import mock

from config_loader import ALL_EMOJIS, DEFAULT_TARGET_EMOJIS, load_config


def test_default_target_emojis_is_nonempty_list():
    """DEFAULT_TARGET_EMOJIS 应为非空字符串列表。"""
    assert isinstance(DEFAULT_TARGET_EMOJIS, list)
    assert len(DEFAULT_TARGET_EMOJIS) > 0
    assert all(isinstance(e, str) for e in DEFAULT_TARGET_EMOJIS)


def test_default_target_emojis_contains_expected():
    """DEFAULT_TARGET_EMOJIS 应包含常见的爱心和点赞表情。"""
    assert '👍' in DEFAULT_TARGET_EMOJIS
    assert '🔥' in DEFAULT_TARGET_EMOJIS


def test_all_emojis_is_nonempty_list():
    """ALL_EMOJIS 应为非空字符串列表。"""
    assert isinstance(ALL_EMOJIS, list)
    assert len(ALL_EMOJIS) > 0
    assert all(isinstance(e, str) for e in ALL_EMOJIS)


def test_default_target_emojis_is_subset_of_all():
    """DEFAULT_TARGET_EMOJIS 应为 ALL_EMOJIS 的子集。"""
    all_set = set(ALL_EMOJIS)
    for emoji in DEFAULT_TARGET_EMOJIS:
        assert emoji in all_set, f"{emoji!r} 在 DEFAULT_TARGET_EMOJIS 中但不在 ALL_EMOJIS 中"


def test_load_config_returns_expected_keys():
    """load_config() 应返回包含所有预期键的字典。"""
    cfg = load_config()
    expected_keys = {
        'api_id', 'api_hash', 'session_name', 'proxy',
        'phone', 'code', 'password', 'channel',
        'start_date', 'end_date', 'target_emojis', 'bot_token',
    }
    assert set(cfg.keys()) == expected_keys


def test_load_config_target_emojis_default():
    """load_config() 默认应返回 DEFAULT_TARGET_EMOJIS。"""
    cfg = load_config()
    assert cfg['target_emojis'] == DEFAULT_TARGET_EMOJIS


def test_load_config_session_name_is_absolute():
    """session_name 应被解析为绝对路径。"""
    cfg = load_config()
    assert os.path.isabs(cfg['session_name'])


def test_load_config_env_override():
    """环境变量应覆盖 TOML 配置值。"""
    with mock.patch.dict(os.environ, {'TELEGRAM_PHONE': '+1234567890'}):
        cfg = load_config()
        assert cfg['phone'] == '+1234567890'


def test_load_config_target_emojis_env_override():
    """环境变量 TARGET_EMOJIS 应覆盖默认目标表情列表。"""
    with mock.patch.dict(os.environ, {'TARGET_EMOJIS': '❤️,👍,🔥'}):
        cfg = load_config()
        assert cfg['target_emojis'] == ['❤️', '👍', '🔥']
