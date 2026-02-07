#!/usr/bin/env python3
"""
Telegram 频道选择器。

命令行交互工具，显示用户已加入的所有频道，
选择后对该频道执行表情统计分析并导出报告。
"""

import asyncio
from datetime import datetime
from typing import Any

from telethon import TelegramClient

from config_loader import TARGET_EMOJIS, load_config

# ==================== 配置区域 ====================
_cfg = load_config()
API_ID = _cfg['api_id']
API_HASH = _cfg['api_hash']
SESSION_NAME = _cfg['session_name']
PROXY = _cfg['proxy']
PHONE = _cfg['phone']
CODE = _cfg['code']
PASSWORD = _cfg['password']

# ===================================================================================


async def create_client() -> TelegramClient | None:
    """
    创建并连接 Telegram 客户端。

    若未授权则自动发起登录流程（手机号 + 验证码 + 两步验证）。

    返回
    ----
    TelegramClient 或 None
        连接成功返回客户端实例；登录失败返回 ``None``。
    """
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH, proxy=PROXY)
    await client.connect()

    if not await client.is_user_authorized():
        sent_code = await client.send_code_request(PHONE)
        if not CODE:
            print("📱 验证码已发送到你的 Telegram")
            print("⚠️  请设置环境变量后重新运行:")
            print("   TELEGRAM_CODE=验证码 uv run python telegram_channel_selector.py")
            await client.disconnect()
            return None
        try:
            await client.sign_in(PHONE, CODE, phone_code_hash=sent_code.phone_code_hash)
        except Exception as e:
            if 'SessionPasswordNeededError' in str(type(e).__name__):
                if not PASSWORD:
                    print("⚠️  需要两步验证密码，请设置环境变量:")
                    print("   TELEGRAM_CODE=验证码 TELEGRAM_PASSWORD=密码 uv run python telegram_channel_selector.py")
                    await client.disconnect()
                    return None
                await client.sign_in(password=PASSWORD)
            else:
                raise e

    return client


async def get_channels(client: TelegramClient) -> list[dict[str, Any]]:
    """
    获取用户已加入的所有频道。

    参数
    ----
    client : TelegramClient
        已连接的 Telegram 客户端。

    返回
    ----
    list[dict]
        频道列表，每项包含 ``id``, ``title``, ``username``。
    """
    channels = []
    async for dialog in client.iter_dialogs():
        if dialog.is_channel:
            entity = dialog.entity
            channels.append({
                'id': entity.id,
                'title': entity.title,
                'username': getattr(entity, 'username', None),
            })
    return channels


def display_channels(channels: list[dict[str, Any]]) -> None:
    """
    在终端显示频道列表。

    参数
    ----
    channels : list[dict]
        频道列表。
    """
    print("\n" + "=" * 60)
    print("📋 你加入的频道列表")
    print("=" * 60)

    for idx, ch in enumerate(channels, 1):
        username_str = f"@{ch['username']}" if ch['username'] else f"ID: {ch['id']}"
        print(f"  [{idx:3d}] {ch['title']}")
        print(f"        {username_str}")

    print("=" * 60)
    print(f"共 {len(channels)} 个频道")


def select_channel(channels: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    交互式频道选择。

    参数
    ----
    channels : list[dict]
        频道列表。

    返回
    ----
    dict 或 None
        用户选中的频道；输入 ``q`` 退出时返回 ``None``。
    """
    while True:
        try:
            choice = input("\n请输入频道编号 (1-{}), 或输入 q 退出: ".format(len(channels)))
            if choice.lower() == 'q':
                return None
            idx = int(choice)
            if 1 <= idx <= len(channels):
                return channels[idx - 1]
            else:
                print(f"❌ 请输入 1 到 {len(channels)} 之间的数字")
        except ValueError:
            print("❌ 请输入有效的数字")


async def analyze_channel(client: TelegramClient, channel: dict[str, Any]) -> None:
    """
    分析选中频道的表情统计。

    遍历频道全部消息，统计目标表情数量，
    显示排行榜并导出报告文件。

    参数
    ----
    client : TelegramClient
        已连接的 Telegram 客户端。
    channel : dict
        频道信息，包含 ``id``, ``title``, ``username``。
    """
    print(f"\n🔍 正在分析频道: {channel['title']}")
    print("-" * 50)

    # 获取频道实体
    try:
        if channel['username']:
            entity = await client.get_entity(channel['username'])
        else:
            entity = await client.get_entity(channel['id'])
    except Exception as e:
        print(f"❌ 获取频道失败: {e}")
        return

    messages_with_reactions = []
    total_checked = 0

    print("⏳ 正在获取消息...")
    async for message in client.iter_messages(entity, limit=None):
        total_checked += 1

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
                'link': f"https://t.me/{entity.username}/{message.id}" if hasattr(entity, 'username') and entity.username else f"[频道ID: {entity.id}]"
            })

        if total_checked % 100 == 0:
            print(f"   已检查 {total_checked} 条消息...", end='\r')

    print(f"\n✅ 共检查 {total_checked} 条消息，找到 {len(messages_with_reactions)} 条有表情的消息")

    # 显示结果并导出
    sorted_messages = display_results(messages_with_reactions, channel['title'])
    if sorted_messages:
        export_to_file(sorted_messages, channel['title'])


def display_results(messages: list[dict[str, Any]], channel_title: str, top_n: int = 10) -> list[dict[str, Any]]:
    """
    在终端显示表情统计排行榜。

    参数
    ----
    messages : list[dict]
        含有表情反应的消息列表。
    channel_title : str
        频道标题。
    top_n : int, 默认 10
        显示前 N 条结果。

    返回
    ----
    list[dict]
        按目标表情数量降序排列的完整消息列表。
    """
    if not messages:
        print("\n❌ 未找到任何有表情的消息")
        return []

    sorted_messages = sorted(messages, key=lambda x: x['reactions'], reverse=True)

    print("\n" + "=" * 80)
    print(f"📊 频道 [{channel_title}] 排序结果（按 ❤️👍 表情数量，显示前 {top_n} 条）")
    print("=" * 80)

    for idx, msg in enumerate(sorted_messages[:top_n], 1):
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
    if total_all > 0:
        print(f"   • 目标表情占比: {total_target/total_all*100:.1f}%")

    return sorted_messages


def export_to_file(messages: list[dict[str, Any]], channel_title: str) -> str | None:
    """
    导出完整统计结果到文本文件。

    参数
    ----
    messages : list[dict]
        排序后的消息列表。
    channel_title : str
        频道标题，用于生成文件名。

    返回
    ----
    str 或 None
        生成的文件路径；消息为空时返回 ``None``。
    """
    if not messages:
        return None

    # 生成安全的文件名
    safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in channel_title)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"report_{safe_title}_{timestamp}.txt"

    with open(filename, 'w', encoding='utf-8') as f:
        f.write("Telegram 频道表情统计报告\n")
        f.write(f"频道: {channel_title}\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")

        for idx, msg in enumerate(messages, 1):
            f.write(f"第 {idx} 名\n")
            f.write(f"时间: {msg['date']}\n")
            f.write(f"浏览: {msg['views']} | 转发: {msg['forwards']}\n")
            f.write(f"目标表情: {msg['reactions']} | 总表情: {msg['total_reactions']}\n")
            f.write(f"内容: {msg['text']}\n")
            f.write(f"链接: {msg['link']}\n")
            f.write("-" * 80 + "\n")

        # 统计汇总
        total_target = sum(m['reactions'] for m in messages)
        total_all = sum(m['total_reactions'] for m in messages)
        f.write("\n统计汇总:\n")
        f.write(f"有表情的消息数: {len(messages)}\n")
        f.write(f"目标表情总数: {total_target}\n")
        f.write(f"所有表情总数: {total_all}\n")
        if total_all > 0:
            f.write(f"目标表情占比: {total_target/total_all*100:.1f}%\n")

    print(f"\n📝 完整报告已保存到: {filename}")
    return filename


async def main() -> None:
    print("🚀 Telegram 频道选择器 - 表情统计工具\n")

    # 连接客户端
    print("🔗 正在连接 Telegram...")
    client = await create_client()
    if not client:
        return

    print("✅ 已登录")

    try:
        # 获取频道列表
        print("\n📡 正在获取频道列表...")
        channels = await get_channels(client)

        if not channels:
            print("❌ 未找到任何频道")
            return

        # 显示频道列表
        display_channels(channels)

        # 用户选择频道
        selected = select_channel(channels)
        if not selected:
            print("\n👋 已退出")
            return

        # 分析选中的频道
        await analyze_channel(client, selected)

    finally:
        await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
