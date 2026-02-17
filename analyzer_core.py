"""
核心分析逻辑，供 Bot / CLI 等多入口复用。
"""

from datetime import datetime

from config_loader import DEFAULT_TARGET_EMOJIS


async def fetch_channel_messages(client, entity, target_emojis=None):
    """
    获取频道所有含 reaction 的消息。

    返回 (messages_list, total_checked)。
    """
    if target_emojis is None:
        target_emojis = DEFAULT_TARGET_EMOJIS

    has_username = hasattr(entity, 'username') and entity.username
    messages = []
    total_checked = 0

    async for message in client.iter_messages(entity, limit=None):
        total_checked += 1

        reaction_details = {}
        if message.reactions:
            for r in message.reactions.results:
                if hasattr(r.reaction, 'emoticon'):
                    reaction_details[r.reaction.emoticon] = r.count

        if reaction_details or message.reactions:
            if has_username:
                link = f"https://t.me/{entity.username}/{message.id}"
            else:
                link = f"https://t.me/c/{entity.id}/{message.id}"

            reaction_count = sum(reaction_details.get(e, 0) for e in target_emojis)

            messages.append({
                'id': message.id,
                'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                'text': message.text[:100] + '...' if message.text and len(message.text) > 100 else (message.text or '[无文字内容]'),
                'views': message.views or 0,
                'forwards': message.forwards or 0,
                'reactions': reaction_count,
                'reaction_details': reaction_details,
                'total_reactions': sum(r.count for r in message.reactions.results) if message.reactions else 0,
                'link': link,
                'has_photo': bool(message.photo),
            })

    return messages, total_checked


def format_top_messages(messages, channel_title, top_n=50):
    """
    将消息列表格式化为适合 Telegram 发送的文本。
    """
    sorted_msgs = sorted(messages, key=lambda x: x['reactions'], reverse=True)[:top_n]
    if not sorted_msgs:
        return f"频道 {channel_title} 没有找到含表情反应的消息。"

    lines = [
        f"📊 {channel_title} — Reaction 排行 Top {len(sorted_msgs)}",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    for idx, msg in enumerate(sorted_msgs, 1):
        lines.append(
            f"{idx}. [{msg['reactions']}❤️ | 👁{msg['views']}] "
            f"{msg['text']}\n{msg['link']}"
        )
    return "\n".join(lines)
