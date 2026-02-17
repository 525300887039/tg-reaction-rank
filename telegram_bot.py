#!/usr/bin/env python3
"""
Telegram Bot 入口：转发频道消息给 Bot，返回该频道 reaction 排行 Top 50。

Bot 仅作为交互前端，实际数据通过 Telethon 用户客户端获取。
"""

import asyncio
import logging
import io
import re

from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel

from analyzer_core import fetch_channel_messages
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

    @bot.on(events.NewMessage)
    async def handler(event):
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
            text = (event.message.text or '').strip()
            # 匹配 https://t.me/xxx 或 @xxx
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
        await event.reply(f"正在分析频道「{title}」，请稍候...")

        try:
            messages, total = await fetch_channel_messages(user_client, entity, cfg['target_emojis'])
        except Exception as e:
            await event.reply(f"获取消息失败: {e}")
            return

        sorted_msgs = sorted(messages, key=lambda x: x['reactions'], reverse=True)[:50]
        if not sorted_msgs:
            await event.reply(f"频道「{title}」没有找到含表情反应的消息。")
            return

        log.info("频道 %s: 检查 %d 条消息，有 reaction %d 条", title, total, len(messages))

        # 发送 header
        total_target = sum(m['reactions'] for m in sorted_msgs)
        total_all = sum(m['total_reactions'] for m in sorted_msgs)
        header = (
            f"📊 {title} — Reaction 排行 Top {len(sorted_msgs)}\n"
            f"消息数: {len(sorted_msgs)} | 目标表情: {total_target} | 总表情: {total_all}"
        )
        await event.reply(header)

        # 逐条发送排行消息
        chat = await event.get_chat()
        for idx, msg in enumerate(sorted_msgs, 1):
            caption = (
                f"第 {idx} 名\n"
                f"时间: {msg['date']}\n"
                f"目标表情: {msg['reactions']} | 总表情: {msg['total_reactions']}\n"
                f"浏览: {msg['views']} | 转发: {msg['forwards']}\n"
                f"内容: {msg['text']}\n"
                f"链接: {msg['link']}"
            )

            sent = False
            if msg.get('has_photo'):
                try:
                    tg_msg = await user_client.get_messages(entity, ids=msg['id'])
                    if tg_msg and tg_msg.photo:
                        buf = io.BytesIO()
                        await user_client.download_media(tg_msg.photo, file=buf)
                        buf.seek(0)
                        buf.name = 'photo.jpg'
                        await bot.send_file(chat, file=buf, caption=caption[:1024], force_document=False)
                        sent = True
                except Exception:
                    pass

            if not sent:
                await bot.send_message(chat, caption[:4096])

            await asyncio.sleep(1)

    log.info("Bot 已启动，等待消息...")
    await bot.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())
