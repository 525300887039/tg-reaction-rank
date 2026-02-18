#!/usr/bin/env python3
"""
Telegram Bot 入口：转发频道消息给 Bot，返回该频道 reaction 排行 Top 50。

Bot 仅作为交互前端，实际数据通过 Telethon 用户客户端获取。
"""

import asyncio
import logging
import os
import re

from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel

from analyzer_core import (
    calc_hotness,
    fetch_channel_messages,
    get_image_dir,
    get_image_path,
    load_raw_cache,
    refilter_reactions,
    save_raw_cache,
)
from config_loader import load_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

cfg = load_config()


async def main():
    if not cfg['bot_token']:
        log.error("未配置 bot_token，请在 config.toml [telegram] 段或环境变量 TELEGRAM_BOT_TOKEN 中设置")
        return

    user_client = TelegramClient(cfg['session_name'], cfg['api_id'], cfg['api_hash'], proxy=cfg['proxy'])
    await user_client.connect()
    if not await user_client.is_user_authorized():
        log.error("用户客户端未授权，请先运行 telegram_channel_selector.py 完成登录")
        await user_client.disconnect()
        return

    bot = TelegramClient('bot_session', cfg['api_id'], cfg['api_hash'], proxy=cfg['proxy'])
    await bot.start(bot_token=cfg['bot_token'])

    pending_sessions = {}

    async def send_results(event, session, messages, total, sort_by_hotness):
        entity = session['entity']
        title = session['title']
        channel_id = session['channel_id']

        if sort_by_hotness:
            sorted_msgs = sorted(messages, key=calc_hotness, reverse=True)[:50]
            sort_label = "热度"
        else:
            sorted_msgs = sorted(messages, key=lambda x: x['reactions'], reverse=True)[:50]
            sort_label = "表情数量"

        if not sorted_msgs:
            await event.reply(f"频道「{title}」没有找到含表情反应的消息。")
            return

        log.info("频道 %s: 检查 %d 条消息，有 reaction %d 条", title, total, len(messages))

        total_target = sum(m['reactions'] for m in sorted_msgs)
        total_all = sum(m['total_reactions'] for m in sorted_msgs)
        header = (
            f"📊 {title} — Reaction 排行 Top {len(sorted_msgs)}（{sort_label}排序）\n"
            f"消息数: {len(sorted_msgs)} | 目标表情: {total_target} | 总表情: {total_all}"
        )
        await event.reply(header)

        chat = await event.get_chat()
        for idx, msg in enumerate(sorted_msgs, 1):
            hotness_line = f"🔥 热度: {calc_hotness(msg):.2f}\n" if sort_by_hotness else ""
            caption = (
                f"第 {idx} 名\n"
                f"时间: {msg['date']}\n"
                f"{hotness_line}"
                f"目标表情: {msg['reactions']} | 总表情: {msg['total_reactions']}\n"
                f"浏览: {msg['views']} | 转发: {msg['forwards']}\n"
                f"内容: {msg['text']}\n"
                f"链接: {msg['link']}"
            )

            sent = False
            if msg.get('has_photo'):
                try:
                    cached_img = get_image_path(channel_id, msg['id'])
                    if cached_img:
                        await bot.send_file(chat, file=cached_img, caption=caption[:1024], force_document=False)
                        sent = True
                    else:
                        tg_msg = await user_client.get_messages(entity, ids=msg['id'])
                        if tg_msg and tg_msg.photo:
                            dest = os.path.join(get_image_dir(channel_id), str(msg['id']))
                            downloaded = await user_client.download_media(tg_msg.photo, file=dest)
                            if downloaded:
                                await bot.send_file(chat, file=downloaded, caption=caption[:1024], force_document=False)
                                sent = True
                except Exception:
                    pass

            if not sent:
                await bot.send_message(chat, caption[:4096])

            await asyncio.sleep(1)

    @bot.on(events.NewMessage)
    async def handler(event):
        user_id = event.sender_id
        text = (event.message.text or '').strip()

        # 第二步：用户选择排序方式 → 加载数据 → 发送结果
        if text in ('1', '2') and user_id in pending_sessions:
            session = pending_sessions.pop(user_id)
            entity = session['entity']
            title = session['title']
            channel_id = session['channel_id']

            raw_messages, total, fetched_at = load_raw_cache(channel_id)
            if raw_messages:
                await event.reply(f"使用缓存数据（{fetched_at}），正在加载「{title}」...")
                refilter_reactions(raw_messages, cfg['target_emojis'])
                messages = raw_messages
            else:
                progress_msg = await event.reply(f"正在分析频道「{title}」… 0%")

                async def on_progress(pct):
                    nonlocal progress_msg
                    new_msg = await event.reply(f"正在分析频道「{title}」… {pct}%")
                    try:
                        await progress_msg.delete()
                    except Exception:
                        pass
                    progress_msg = new_msg

                try:
                    messages, total = await fetch_channel_messages(
                        user_client, entity, cfg['target_emojis'], on_progress=on_progress,
                    )
                except Exception as e:
                    await event.reply(f"获取消息失败: {e}")
                    return
                try:
                    await progress_msg.delete()
                except Exception:
                    pass
                if messages:
                    save_raw_cache(channel_id, title, messages, total)

            if not messages:
                await event.reply(f"频道「{title}」没有找到含表情反应的消息。")
                return

            await send_results(event, session, messages, total, sort_by_hotness=(text == '1'))
            return

        entity = None

        # 方式1：转发的频道消息
        fwd = event.message.fwd_from
        if fwd and fwd.from_id and isinstance(fwd.from_id, PeerChannel):
            try:
                entity = await user_client.get_entity(PeerChannel(fwd.from_id.channel_id))
            except Exception as e:
                await event.reply(f"无法访问该频道（可能未加入）: {e}")
                return

        # 方式2：链接或用户名
        if entity is None:
            m = re.match(r'(?:https?://t\.me/|@)([a-zA-Z][\w]{3,})', text)
            if m:
                try:
                    entity = await user_client.get_entity(m.group(1))
                except Exception as e:
                    await event.reply(f"无法访问该频道（可能未加入或用户名无效）: {e}")
                    return

        if entity is None:
            await event.reply(
                "请通过以下任一方式告诉我要分析的频道：\n"
                "1. 转发该频道的任意一条消息\n"
                "2. 发送频道链接，如 https://t.me/channel_name\n"
                "3. 发送频道用户名，如 @channel_name"
            )
            return

        title = getattr(entity, 'title', str(getattr(entity, 'id', '?')))
        channel_id = entity.id

        pending_sessions[user_id] = {
            'entity': entity, 'title': title, 'channel_id': channel_id,
        }
        await event.reply(
            "请选择排序方式：\n"
            "1. 🔥 热度排序\n"
            "2. ❤️ 表情数量排序\n\n"
            "💡 热度 = log(1+表情×0.7+转发×0.3) / (天数+2)^0.3"
        )

    log.info("Bot 已启动，等待消息...")
    await bot.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())
