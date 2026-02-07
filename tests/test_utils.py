"""工具函数测试。"""

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
