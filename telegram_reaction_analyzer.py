#!/usr/bin/env python3
"""
Telegram 频道消息表情统计工具。

通过 MTProto API 获取指定频道的全部历史消息，
统计目标表情（爱心、点赞等）反应数量并生成排行榜。
"""

import asyncio
from datetime import datetime
from typing import Any

from telethon import TelegramClient

from config_loader import load_config

# ==================== 配置区域 ====================
_cfg = load_config()
API_ID = _cfg['api_id']
API_HASH = _cfg['api_hash']
SESSION_NAME = _cfg['session_name']
PROXY = _cfg['proxy']
PHONE = _cfg['phone']
CODE = _cfg['code']
PASSWORD = _cfg['password']
CHANNEL = _cfg['channel']
START_DATE = _cfg['start_date']
END_DATE = _cfg['end_date']
TARGET_EMOJIS = _cfg['target_emojis']

# =================================================


def code_callback() -> str:
    """
    验证码回调函数。

    返回
    ----
    str
        用户设置的验证码。

    异常
    ----
    ValueError
        未设置验证码时抛出。
    """
    if CODE:
        return CODE
    raise ValueError("请设置环境变量 TELEGRAM_CODE=你收到的验证码")


async def get_messages_with_reactions() -> list[dict[str, Any]]:
    """
    获取频道全部历史消息及其表情反应。

    连接 Telegram 并遍历目标频道的所有消息，
    提取含有表情反应的消息及其统计数据。

    返回
    ----
    list[dict]
        消息列表，每项包含 ``id``, ``date``, ``text``,
        ``views``, ``forwards``, ``reactions``,
        ``total_reactions``, ``link``。
    """
    
    print("🔍 正在连接 Telegram...")
    print(f"📢 目标频道: {CHANNEL}")
    print("📅 时间范围: 全部历史消息")
    print("-" * 50)
    
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH, proxy=PROXY)
    await client.connect()

    if not await client.is_user_authorized():
        sent_code = await client.send_code_request(PHONE)
        if not CODE:
            print("📱 验证码已发送到你的 Telegram")
            print("⚠️  请设置环境变量后重新运行:")
            print("   TELEGRAM_CODE=你收到的验证码 TELEGRAM_PASSWORD=你的两步验证密码 uv run python telegram_reaction_analyzer.py")
            await client.disconnect()
            return []
        try:
            await client.sign_in(PHONE, CODE, phone_code_hash=sent_code.phone_code_hash)
        except Exception as e:
            if 'SessionPasswordNeededError' in str(type(e).__name__):
                if not PASSWORD:
                    print("⚠️  需要两步验证密码，请设置环境变量:")
                    print("   TELEGRAM_CODE=验证码 TELEGRAM_PASSWORD=密码 uv run python telegram_reaction_analyzer.py")
                    await client.disconnect()
                    return []
                await client.sign_in(password=PASSWORD)
            else:
                raise e

    print("✅ 已登录")

    # 获取频道实体
    try:
        channel = await client.get_entity(CHANNEL)
        print(f"📋 频道: {channel.title}")
    except Exception as e:
        print(f"❌ 获取频道失败: {e}")
        await client.disconnect()
        return []

    messages_with_reactions = []
    total_checked = 0

    # 获取消息（不限制时间，获取全部历史）
    print("\n⏳ 正在获取消息...")
    async for message in client.iter_messages(
        channel,
        limit=None  # 不限制数量，获取所有历史消息
    ):
        total_checked += 1

        # 统计目标表情数量
        reaction_count = 0
        if message.reactions:
            for reaction in message.reactions.results:
                if hasattr(reaction.reaction, 'emoticon'):
                    emoji = reaction.reaction.emoticon
                    if emoji in TARGET_EMOJIS:
                        reaction_count += reaction.count

        if reaction_count > 0 or message.reactions:
            messages_with_reactions.append({
                'id': message.id,
                'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                'text': message.text[:100] + '...' if message.text and len(message.text) > 100 else (message.text or '[无文字内容]'),
                'views': message.views or 0,
                'forwards': message.forwards or 0,
                'reactions': reaction_count,
                'total_reactions': sum(r.count for r in message.reactions.results) if message.reactions else 0,
                'link': f"https://t.me/{channel.username}/{message.id}" if hasattr(channel, 'username') and channel.username else f"[频道ID: {channel.id}]"
            })

        if total_checked % 100 == 0:
            print(f"   已检查 {total_checked} 条消息...", end='\r')

    print(f"\n✅ 共检查 {total_checked} 条消息，找到 {len(messages_with_reactions)} 条有表情的消息")

    await client.disconnect()
    return messages_with_reactions


def sort_and_display(messages: list[dict[str, Any]], top_n: int = 10) -> list[dict[str, Any]]:
    """
    按目标表情数量排序并在终端显示排行榜。

    参数
    ----
    messages : list[dict]
        含有表情反应的消息列表。
    top_n : int, 默认 10
        显示前 N 条结果。

    返回
    ----
    list[dict]
        排序后的前 N 条消息。
    """
    
    if not messages:
        print("\n❌ 未找到任何消息")
        return []
    
    # 按目标表情数量降序排序
    sorted_messages = sorted(messages, key=lambda x: x['reactions'], reverse=True)
    
    print("\n" + "=" * 80)
    print(f"📊 排序结果（按 ❤️👍 表情数量从高到低，显示前 {top_n} 条）")
    print("=" * 80)
    
    top_messages = sorted_messages[:top_n]
    for idx, msg in enumerate(top_messages, 1):
        print(f"\n🏆 第 {idx} 名")
        print(f"   📅 时间: {msg['date']}")
        print(f"   👁️  浏览: {msg['views']} | 📤 转发: {msg['forwards']}")
        print(f"   ❤️👍 目标表情: {msg['reactions']} | 📊 总表情: {msg['total_reactions']}")
        print(f"   📝 内容: {msg['text'][:200]}{'...' if len(msg['text']) > 200 else ''}")
        print(f"   🔗 链接: {msg['link']}")
        print("-" * 80)
    
    # 统计信息
    total_target = sum(m['reactions'] for m in messages)
    total_all = sum(m['total_reactions'] for m in messages)
    
    print("\n📈 统计汇总:")
    print(f"   • 有表情的消息数: {len(messages)}")
    print(f"   • 目标表情总数: {total_target}")
    print(f"   • 所有表情总数: {total_all}")
    print(f"   • 目标表情占比: {total_target/total_all*100:.1f}%" if total_all > 0 else "")
    
    return top_messages


async def export_to_file(messages: list[dict[str, Any]], filename: str = 'telegram_reactions_report.txt') -> None:
    """
    导出统计结果到文本文件。

    参数
    ----
    messages : list[dict]
        含有表情反应的消息列表。
    filename : str, 默认 ``'telegram_reactions_report.txt'``
        输出文件路径。
    """
    sorted_messages = sorted(messages, key=lambda x: x['reactions'], reverse=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("Telegram 频道表情统计报告\n")
        f.write(f"频道: {CHANNEL}\n")
        f.write(f"时间范围: {START_DATE} 至 {END_DATE}\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        for idx, msg in enumerate(sorted_messages, 1):
            f.write(f"第 {idx} 名\n")
            f.write(f"时间: {msg['date']}\n")
            f.write(f"浏览: {msg['views']} | 转发: {msg['forwards']}\n")
            f.write(f"目标表情: {msg['reactions']} | 总表情: {msg['total_reactions']}\n")
            f.write(f"内容: {msg['text']}\n")
            f.write(f"链接: {msg['link']}\n")
            f.write("-" * 80 + "\n")
    
    print(f"\n📝 已导出到文件: {filename}")


async def main() -> None:
    print("🚀 Telegram 频道消息表情统计工具\n")
    
    # 检查配置
    if API_ID == 'YOUR_API_ID' or API_HASH == 'YOUR_API_HASH':
        print("⚠️  请先配置 API_ID 和 API_HASH！")
        print("   1. 访问 https://my.telegram.org/apps 创建应用")
        print("   2. 编辑脚本开头的配置区域，或使用环境变量")
        print("\n环境变量设置方式:")
        print("   export TELEGRAM_API_ID=你的数字ID")
        print("   export TELEGRAM_API_HASH=你的hash字符串")
        print("   export TELEGRAM_CHANNEL=@频道名")
        return
    
    # 获取消息
    messages = await get_messages_with_reactions()
    
    # 排序显示（显示前10条）
    sort_and_display(messages, top_n=10)
    
    # 导出到文件
    if messages:
        await export_to_file(messages)


if __name__ == '__main__':
    asyncio.run(main())
