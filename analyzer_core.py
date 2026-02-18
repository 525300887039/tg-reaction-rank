"""
核心分析逻辑，供 Bot / CLI 等多入口复用。
"""

import glob
import json
import math
import os
from datetime import datetime
from typing import Any

from config_loader import DEFAULT_TARGET_EMOJIS


def calc_hotness(msg: dict) -> float:
    """计算消息热度值（Reddit 风格加法公式）。"""
    score = msg['reactions'] * 0.7 + msg['forwards'] * 0.3
    epoch = datetime(2020, 1, 1)
    days = (datetime.strptime(msg['date'], '%Y-%m-%d %H:%M:%S') - epoch).total_seconds() / 86400
    return math.log10(max(score, 1)) + days / 800


def refilter_reactions(messages: list[dict[str, Any]], target_emojis: list[str]) -> list[dict[str, Any]]:
    """根据目标表情列表重新计算每条消息的 reactions 值。"""
    for msg in messages:
        details = msg.get('reaction_details')
        if details is not None:
            msg['reactions'] = sum(details.get(e, 0) for e in target_emojis)
    return messages


def get_image_dir(channel_id: int) -> str:
    """获取图片缓存目录路径，若不存在则自动创建。"""
    img_dir = os.path.join(os.path.dirname(__file__), 'cache', 'images', str(channel_id))
    os.makedirs(img_dir, exist_ok=True)
    return img_dir


def get_image_path(channel_id: int, message_id: int) -> str | None:
    """查找已下载的消息配图，未找到时返回 None。"""
    img_dir = get_image_dir(channel_id)
    matches = glob.glob(os.path.join(img_dir, f'{message_id}.*'))
    return matches[0] if matches else None


def get_raw_cache_path(channel_id: int) -> str:
    """获取原始数据缓存文件路径。"""
    cache_dir = os.path.join(os.path.dirname(__file__), 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f'raw_{channel_id}.json')


def save_raw_cache(channel_id: int, channel_title: str, messages: list[dict[str, Any]], total_checked: int) -> None:
    """将原始消息数据写入缓存。"""
    path = get_raw_cache_path(channel_id)
    data = {
        'channel_id': channel_id,
        'channel_title': channel_title,
        'fetched_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_checked': total_checked,
        'messages': messages,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_raw_cache(channel_id: int) -> tuple[list[dict[str, Any]] | None, int | None, str | None]:
    """读取原始数据缓存，返回 (messages, total_checked, fetched_at)。"""
    path = get_raw_cache_path(channel_id)
    if not os.path.exists(path):
        return None, None, None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data['messages'], data['total_checked'], data['fetched_at']
    except (json.JSONDecodeError, KeyError):
        return None, None, None


async def fetch_channel_messages(client, entity, target_emojis=None, on_progress=None):
    """
    获取频道所有含 reaction 的消息。

    返回 (messages_list, total_checked)。
    on_progress: 可选异步回调，签名 async (percent: int) -> None，每跨越 10% 调用一次。
    """
    if target_emojis is None:
        target_emojis = DEFAULT_TARGET_EMOJIS

    has_username = hasattr(entity, 'username') and entity.username
    messages = []
    total_checked = 0

    estimated_total = (await client.get_messages(entity, limit=0)).total
    last_reported = 0

    async for message in client.iter_messages(entity, limit=None):
        total_checked += 1
        if on_progress and estimated_total:
            pct = total_checked * 100 // estimated_total
            if pct >= last_reported + 10:
                last_reported = pct // 10 * 10
                await on_progress(last_reported)

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
