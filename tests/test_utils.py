"""工具函数测试。"""

from analyzer_core import refilter_reactions
from streamlit_app import generate_report


def test_generate_report_basic():
    """generate_report 应生成包含关键信息的字符串。"""
    messages = [
        {
            'id': 1,
            'date': '2026-01-15 12:00:00',
            'text': 'Test message',
            'views': 100,
            'forwards': 5,
            'reactions': 42,
            'total_reactions': 50,
            'link': 'https://t.me/test/1',
        }
    ]
    report = generate_report(messages, 'Test Channel')

    assert isinstance(report, str)
    assert 'Test Channel' in report
    assert '第 1 名' in report
    assert 'Test message' in report
    assert '42' in report


def test_refilter_reactions_basic():
    """refilter_reactions 应根据目标表情重新计算 reactions。"""
    messages = [
        {
            'id': 1,
            'reactions': 0,
            'reaction_details': {'❤️': 10, '👍': 5, '🔥': 3},
        },
    ]
    refilter_reactions(messages, ['❤️', '👍'])
    assert messages[0]['reactions'] == 15


def test_refilter_reactions_empty_target():
    """目标表情为空时 reactions 应为 0。"""
    messages = [
        {
            'id': 1,
            'reactions': 99,
            'reaction_details': {'❤️': 10, '👍': 5},
        },
    ]
    refilter_reactions(messages, [])
    assert messages[0]['reactions'] == 0


def test_refilter_reactions_old_cache_preserved():
    """缺少 reaction_details 的旧缓存消息应保留原有 reactions 值。"""
    messages = [
        {
            'id': 1,
            'reactions': 42,
        },
    ]
    refilter_reactions(messages, ['❤️', '👍'])
    assert messages[0]['reactions'] == 42
