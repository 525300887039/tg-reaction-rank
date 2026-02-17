#!/usr/bin/env python3
"""
Telegram 频道表情统计分析 - Streamlit Web 界面。

提供可视化的频道选择、表情统计分析、排行榜展示与报告导出功能。
"""

import asyncio
import html
import json
import os
import shutil
import threading
from collections.abc import Coroutine
from datetime import datetime
from typing import Any

import streamlit as st
from telethon import TelegramClient

from analyzer_core import (
    calc_hotness,
    get_image_dir,
    get_image_path,
    get_raw_cache_path,
    load_raw_cache,
    refilter_reactions,
    save_raw_cache,
)
from config_loader import ALL_EMOJIS, DEFAULT_TARGET_EMOJIS, load_config

# 独立线程事件循环，替代 nest-asyncio
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()

# ==================== 配置区域 ====================
_cfg = load_config()
API_ID = _cfg['api_id']
API_HASH = _cfg['api_hash']
SESSION_NAME = _cfg['session_name']
PROXY = _cfg['proxy']

# =================================================


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """在同步上下文中运行异步协程（通过独立线程的事件循环）。"""
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result()



def get_cache_path(channel_id: int) -> str:
    """
    获取分析结果缓存文件路径。

    若 ``cache/`` 目录不存在则自动创建。

    参数
    ----
    channel_id : int
        频道 ID。

    返回
    ----
    str
        缓存文件的绝对路径。
    """
    cache_dir = os.path.join(os.path.dirname(__file__), 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f'channel_{channel_id}.json')


def load_cache(channel_id: int) -> tuple[list[dict[str, Any]] | None, str | None]:
    """
    读取分析结果缓存。

    参数
    ----
    channel_id : int
        频道 ID。

    返回
    ----
    tuple[list | None, str | None]
        ``(results, analyzed_at)``；缓存不存在或损坏时返回 ``(None, None)``。
    """
    path = get_cache_path(channel_id)
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        results = data['results']
        # 验证 image_path 是否仍然存在
        for msg in results:
            img = msg.get('image_path')
            if img and not os.path.exists(img):
                msg['image_path'] = None
        return results, data['analyzed_at']
    except (json.JSONDecodeError, KeyError):
        return None, None


def save_cache(channel_id: int, channel_title: str, results: list[dict[str, Any]]) -> None:
    """
    将分析结果写入缓存文件。

    参数
    ----
    channel_id : int
        频道 ID。
    channel_title : str
        频道标题。
    results : list[dict]
        排序后的消息列表。
    """
    path = get_cache_path(channel_id)
    data = {
        'channel_id': channel_id,
        'channel_title': channel_title,
        'analyzed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'results': results,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)






def clear_result_cache(channel_id: int) -> None:
    """
    清除指定频道的结果缓存和已下载图片。

    参数
    ----
    channel_id : int
        频道 ID。
    """
    path = get_cache_path(channel_id)
    if os.path.exists(path):
        os.remove(path)
    img_dir = os.path.join(os.path.dirname(__file__), 'cache', 'images', str(channel_id))
    if os.path.exists(img_dir):
        shutil.rmtree(img_dir)


def clear_all_cache(channel_id: int) -> None:
    """
    清除指定频道的所有缓存。

    包括原始数据缓存、结果缓存和已下载图片。

    参数
    ----
    channel_id : int
        频道 ID。
    """
    clear_result_cache(channel_id)
    raw_path = get_raw_cache_path(channel_id)
    if os.path.exists(raw_path):
        os.remove(raw_path)


async def check_connection() -> tuple[bool, str | None]:
    """
    检查当前 session 是否已登录授权。

    返回
    ----
    tuple[bool, str | None]
        ``(authorized, error)``；连接异常时 ``authorized`` 为 False，
        ``error`` 为错误信息。
    """
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH, proxy=PROXY)
    try:
        await client.connect()
        authorized = await client.is_user_authorized()
        await client.disconnect()
        return authorized, None
    except Exception as e:
        return False, str(e)


async def fetch_channels() -> tuple[list[dict[str, Any]], str | None]:
    """
    获取用户已加入的所有频道。

    返回
    ----
    tuple[list[dict], str | None]
        ``(channels, error)``；每个频道为包含
        ``id``, ``title``, ``username`` 的字典。
    """
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH, proxy=PROXY)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return [], "未授权"

        channels = []
        async for dialog in client.iter_dialogs():
            if dialog.is_channel:
                entity = dialog.entity
                channels.append({
                    'id': entity.id,
                    'title': entity.title,
                    'username': getattr(entity, 'username', None),
                })
        await client.disconnect()
        return channels, None
    except Exception as e:
        return [], str(e)


async def fetch_messages_async(channel: dict[str, Any], progress_bar: Any, status_text: Any) -> tuple[list[dict[str, Any]] | None, int | None, str | None]:
    """
    从 Telegram 获取频道的原始消息数据。

    遍历频道全部消息，提取含有表情反应的消息及其统计信息。
    此为分析流程的第一阶段，返回未排序、无图片的原始数据。

    参数
    ----
    channel : dict
        频道信息，包含 ``id``, ``title``, ``username``。
    progress_bar : streamlit.delta_generator.DeltaGenerator
        Streamlit 进度条组件。
    status_text : streamlit.delta_generator.DeltaGenerator
        Streamlit 状态文本组件。

    返回
    ----
    tuple[list[dict] | None, int | None, str | None]
        ``(messages, total_checked, error)``。
    """
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH, proxy=PROXY)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return None, None, "未授权"

        if channel['username']:
            entity = await client.get_entity(channel['username'])
        else:
            entity = await client.get_entity(channel['id'])

        messages_with_reactions = []
        total_checked = 0

        status_text.text("正在获取消息...")

        async for message in client.iter_messages(entity, limit=None):
            total_checked += 1

            reaction_details: dict[str, int] = {}
            if message.reactions:
                for reaction in message.reactions.results:
                    if hasattr(reaction.reaction, 'emoticon'):
                        emoji = reaction.reaction.emoticon
                        reaction_details[emoji] = reaction.count

            if reaction_details or message.reactions:
                if hasattr(entity, 'username') and entity.username:
                    msg_link = f"https://t.me/{entity.username}/{message.id}"
                else:
                    msg_link = f"https://t.me/c/{entity.id}/{message.id}"

                target_emojis = st.session_state.get('target_emojis', DEFAULT_TARGET_EMOJIS)
                reaction_count = sum(reaction_details.get(e, 0) for e in target_emojis)

                messages_with_reactions.append({
                    'id': message.id,
                    'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                    'text': message.text[:100] + '...' if message.text and len(message.text) > 100 else (message.text or '[无文字内容]'),
                    'views': message.views or 0,
                    'forwards': message.forwards or 0,
                    'reactions': reaction_count,
                    'reaction_details': reaction_details,
                    'total_reactions': sum(r.count for r in message.reactions.results) if message.reactions else 0,
                    'link': msg_link,
                    'has_photo': bool(message.photo),
                    'image_path': None,
                })

            if total_checked % 50 == 0:
                status_text.text(f"已检查 {total_checked} 条消息...")
                progress_bar.progress(min(total_checked / 10000, 0.99))

        progress_bar.progress(1.0)
        status_text.text(f"完成！共检查 {total_checked} 条消息")

        await client.disconnect()
        return messages_with_reactions, total_checked, None
    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        return None, None, f"获取频道失败: {e}"


async def process_results_async(channel: dict[str, Any], raw_messages: list[dict[str, Any]], progress_bar: Any, status_text: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    """
    对原始消息排序并为前 50 名下载配图。

    此为分析流程的第二阶段。

    参数
    ----
    channel : dict
        频道信息，包含 ``id``, ``title``, ``username``。
    raw_messages : list[dict]
        第一阶段获取的原始消息列表。
    progress_bar : streamlit.delta_generator.DeltaGenerator
        Streamlit 进度条组件。
    status_text : streamlit.delta_generator.DeltaGenerator
        Streamlit 状态文本组件。

    返回
    ----
    tuple[list[dict] | None, str | None]
        ``(results, error)``。
    """
    status_text.text("正在排序并下载图片...")
    results = sorted(raw_messages, key=lambda x: x['reactions'], reverse=True)

    # 为每条消息确保有 image_path 字段
    for msg in results:
        if 'image_path' not in msg:
            msg['image_path'] = None

    # 筛选需要下载图片的消息
    to_download = [msg for msg in results[:50] if msg.get('has_photo')]
    # 检查已有缓存图片
    need_telegram = False
    for msg in to_download:
        existing = get_image_path(channel['id'], msg['id'])
        if existing:
            msg['image_path'] = existing
        else:
            need_telegram = True

    if need_telegram:
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH, proxy=PROXY)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return None, "未授权"

            if channel['username']:
                entity = await client.get_entity(channel['username'])
            else:
                entity = await client.get_entity(channel['id'])

            for i, msg in enumerate(to_download):
                if msg['image_path']:
                    continue
                img_dir = get_image_dir(channel['id'])
                dest_path = os.path.join(img_dir, str(msg['id']))
                try:
                    tg_msg = await client.get_messages(entity, ids=msg['id'])
                    if tg_msg and tg_msg.photo:
                        downloaded = await client.download_media(tg_msg.photo, file=dest_path)
                        if downloaded:
                            msg['image_path'] = downloaded
                except Exception:
                    pass
                progress_bar.progress(min((i + 1) / len(to_download), 0.99))

            await client.disconnect()
        except Exception as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            return None, f"下载图片失败: {e}"

    progress_bar.progress(1.0)
    status_text.text("处理完成！")
    return results, None


def generate_report(messages: list[dict[str, Any]], channel_title: str) -> str:
    """
    生成纯文本格式的统计报告。

    参数
    ----
    messages : list[dict]
        排序后的消息列表。
    channel_title : str
        频道标题。

    返回
    ----
    str
        完整的报告文本。
    """
    lines = []
    lines.append("Telegram 频道表情统计报告")
    lines.append(f"频道: {channel_title}")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 80)
    lines.append("")

    for idx, msg in enumerate(messages, 1):
        lines.append(f"第 {idx} 名")
        lines.append(f"时间: {msg['date']}")
        lines.append(f"浏览: {msg['views']} | 转发: {msg['forwards']}")
        lines.append(f"目标表情: {msg['reactions']} | 总表情: {msg['total_reactions']}")
        lines.append(f"内容: {msg['text']}")
        lines.append(f"链接: {msg['link']}")
        lines.append("-" * 80)

    total_target = sum(m['reactions'] for m in messages)
    total_all = sum(m['total_reactions'] for m in messages)
    lines.append("")
    lines.append("统计汇总:")
    lines.append(f"有表情的消息数: {len(messages)}")
    lines.append(f"目标表情总数: {total_target}")
    lines.append(f"所有表情总数: {total_all}")
    if total_all > 0:
        lines.append(f"目标表情占比: {total_target/total_all*100:.1f}%")

    return "\n".join(lines)


async def send_report_to_saved(messages: list[dict[str, Any]], channel_title: str) -> tuple[bool, str | None]:
    """
    将报告逐条发送到 Telegram 收藏夹。

    每条消息间隔 1 秒以避免触发频率限制，支持附带配图。

    参数
    ----
    messages : list[dict]
        排序后的消息列表。
    channel_title : str
        频道标题。

    返回
    ----
    tuple[bool, str | None]
        ``(success, error)``。
    """
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH, proxy=PROXY)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return False, "未授权"

        # 发送标题/汇总信息
        total_target = sum(m['reactions'] for m in messages)
        total_all = sum(m['total_reactions'] for m in messages)
        header = (
            f"Telegram 频道表情统计报告\n"
            f"频道: {channel_title}\n"
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'=' * 40}\n"
            f"消息数: {len(messages)} | 目标表情: {total_target} | 总表情: {total_all}"
        )
        await client.send_message('me', header)

        # 逐条发送排行消息，每条间隔 1 秒避免触发 Telegram 频率限制
        for idx, msg in enumerate(messages, 1):
            text = (
                f"第 {idx} 名\n"
                f"时间: {msg['date']}\n"
                f"目标表情: {msg['reactions']} | 总表情: {msg['total_reactions']}\n"
                f"浏览: {msg['views']} | 转发: {msg['forwards']}\n"
                f"内容: {msg['text']}\n"
                f"链接: {msg['link']}"
            )

            image_path = msg.get('image_path')
            if image_path and os.path.exists(image_path):
                await client.send_file('me', file=image_path, caption=text[:1024])
            else:
                await client.send_message('me', text[:4000])

            await asyncio.sleep(1)

        await client.disconnect()
        return True, None
    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        return False, str(e)


CUSTOM_CSS = """
<style>
/* Metric 卡片 */
div[data-testid="stMetric"] {
    background: linear-gradient(135deg, #ffffff 0%, #f0f4ff 100%);
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 2px 8px rgba(0, 136, 204, 0.1);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
div[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(0, 136, 204, 0.2);
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #0088cc;
}

/* 侧边栏 */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0088cc 0%, #006699 100%);
}
section[data-testid="stSidebar"] * {
    color: #ffffff !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background-color: rgba(255, 255, 255, 0.2);
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.4);
    border-radius: 8px;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background-color: rgba(255, 255, 255, 0.3);
    border-color: #ffffff;
}
section[data-testid="stSidebar"] .stAlert {
    background-color: rgba(255, 255, 255, 0.15);
    border: none;
}

/* 排行榜卡片 */
.rank-card {
    background: #ffffff;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 16px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    border-left: 4px solid #0088cc;
}
.rank-card:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

/* 排名徽章 */
.rank-badge {
    display: inline-block;
    background: linear-gradient(135deg, #0088cc, #006699);
    color: #ffffff !important;
    padding: 4px 14px;
    border-radius: 20px;
    font-weight: 700;
    font-size: 0.9em;
    margin-right: 10px;
}
.rank-badge.top3 {
    background: linear-gradient(135deg, #f0a500, #d4900a);
}

/* 统计标签 */
.rank-stat {
    display: inline-block;
    background: #f0f2f5;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.85em;
    margin-right: 6px;
    margin-top: 6px;
    color: #555;
}
.rank-stat.primary {
    background: #e6f3ff;
    color: #0088cc;
    font-weight: 600;
}

/* 欢迎页 */
.welcome-box {
    background: linear-gradient(135deg, #e6f3ff 0%, #f0f8ff 100%);
    border-radius: 16px;
    padding: 40px;
    text-align: center;
    max-width: 600px;
    margin: 40px auto;
    box-shadow: 0 4px 12px rgba(0, 136, 204, 0.1);
}
.welcome-box h2 {
    color: #0088cc;
    margin-bottom: 24px;
}
.welcome-box .step {
    display: flex;
    align-items: center;
    text-align: left;
    margin: 12px 0;
    padding: 10px 16px;
    background: rgba(255, 255, 255, 0.7);
    border-radius: 10px;
}
.welcome-box .step-num {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: #0088cc;
    color: #ffffff !important;
    border-radius: 50%;
    font-weight: 700;
    margin-right: 14px;
    flex-shrink: 0;
}
.welcome-box .step span:last-child {
    color: #1a1a2e;
}

/* 结果标题横幅 */
.result-header {
    background: linear-gradient(135deg, #0088cc 0%, #006699 100%);
    color: #ffffff !important;
    padding: 20px 28px;
    border-radius: 12px;
    margin-bottom: 20px;
}
.result-header h2 {
    margin: 0;
    color: #ffffff !important;
    font-size: 1.5em;
}
.result-header p {
    margin: 6px 0 0 0;
    color: rgba(255, 255, 255, 0.85) !important;
    font-size: 0.9em;
}
</style>
"""


def main() -> None:
    st.set_page_config(
        page_title="Telegram 频道分析器",
        page_icon="📊",
        layout="wide"
    )

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    st.markdown(
        '<h1 style="margin-bottom:2px;">📊 Telegram 频道表情统计分析</h1>'
        '<p style="color:#666; font-size:1.1em; margin-top:0;">'
        '分析频道消息的表情反应数据，发现最受欢迎的内容</p>',
        unsafe_allow_html=True,
    )

    # 初始化 session state
    if 'connected' not in st.session_state:
        st.session_state.connected = False
    if 'channels' not in st.session_state:
        st.session_state.channels = []
    if 'results' not in st.session_state:
        st.session_state.results = None
    if 'target_emojis' not in st.session_state:
        st.session_state.target_emojis = list(DEFAULT_TARGET_EMOJIS)

    # 侧边栏 - 连接状态
    with st.sidebar:
        st.markdown(
            '<div style="text-align:center; padding:10px 0 16px;">'
            '<span style="font-size:2em;">✈️</span><br>'
            '<strong style="font-size:1.2em;">Telegram 连接</strong></div>',
            unsafe_allow_html=True,
        )

        if not st.session_state.connected:
            with st.spinner("正在连接 Telegram..."):
                authorized, error = run_async(check_connection())
                if error:
                    st.error(f"连接失败: {error}")
                elif not authorized:
                    st.error("未授权，请先在命令行运行 telegram_channel_selector.py 完成登录")
                else:
                    channels, err = run_async(fetch_channels())
                    if err:
                        st.error(f"获取频道失败: {err}")
                    else:
                        st.session_state.connected = True
                        st.session_state.channels = channels
                        st.rerun()
            if not st.session_state.connected:
                if st.button("重试连接", type="primary", width="stretch"):
                    st.rerun()
        else:
            st.success(f"已连接 · 已加载 {len(st.session_state.channels)} 个频道")
            if st.button("断开连接", width="stretch"):
                st.session_state.connected = False
                st.session_state.channels = []
                st.session_state.results = None
                st.rerun()

        # 目标表情设置
        with st.expander("目标表情设置"):
            selected = st.multiselect(
                "选择要统计的表情",
                options=ALL_EMOJIS,
                default=st.session_state.target_emojis,
                key="emoji_selector",
            )
            if selected != st.session_state.target_emojis:
                st.session_state.target_emojis = selected
                if st.session_state.results is not None:
                    refilter_reactions(st.session_state.results, selected)
            if st.button("恢复默认", width="stretch"):
                st.session_state.target_emojis = list(DEFAULT_TARGET_EMOJIS)
                if st.session_state.results is not None:
                    refilter_reactions(st.session_state.results, DEFAULT_TARGET_EMOJIS)
                st.rerun()

    # 主界面
    if not st.session_state.connected:
        st.markdown(
            '<div class="welcome-box">'
            '<h2>欢迎使用频道分析器</h2>'
            '<p style="color:#555; margin-bottom:24px;">按照以下步骤开始分析</p>'
            '<div class="step"><span class="step-num">1</span>'
            '<span>确保已在命令行完成 Telegram 登录授权</span></div>'
            '<div class="step"><span class="step-num">2</span>'
            '<span>点击侧边栏的「连接 Telegram」按钮</span></div>'
            '<div class="step"><span class="step-num">3</span>'
            '<span>选择要分析的频道</span></div>'
            '<div class="step"><span class="step-num">4</span>'
            '<span>查看分析结果并导出报告</span></div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # 频道选择
    st.markdown("### 选择频道")

    if not st.session_state.channels:
        st.warning("未找到任何频道")
        return

    channel_labels = []
    for ch in st.session_state.channels:
        if ch['username']:
            channel_labels.append(f"{ch['title']}  (@{ch['username']})")
        else:
            channel_labels.append(f"{ch['title']}  (ID: {ch['id']})")

    selected_name = st.selectbox(
        "选择要分析的频道",
        options=channel_labels,
        index=None,
        placeholder="请选择一个频道...",
    )

    if selected_name:
        selected_channel = st.session_state.channels[channel_labels.index(selected_name)]

        col_kw, col_sort, col_ck = st.columns([3, 1.5, 1])
        with col_kw:
            keyword = st.text_input("关键词筛选", value="", placeholder="留空则显示全部消息")
        with col_sort:
            sort_method = st.selectbox("排序方式", ["目标表情数量", "热度"], key="sort_method")
            if sort_method == "热度":
                st.caption("热度 = log(1 + 表情×0.7 + 转发×0.3) / (天数+2)^0.3")
        with col_ck:
            st.markdown("<br>", unsafe_allow_html=True)
            force_reanalyze = st.checkbox("忽略缓存")

        if st.button("开始分析", type="primary"):
            st.session_state.keyword = keyword
            channel_id = selected_channel['id']
            cached_results, analyzed_at = load_cache(channel_id)

            if cached_results is not None and not force_reanalyze:
                # 层级1：有结果缓存且未忽略 → 直接使用
                refilter_reactions(cached_results, st.session_state.target_emojis)
                st.session_state.results = cached_results
                st.session_state.selected_channel = selected_channel
                st.session_state.cache_time = analyzed_at
                st.rerun()
            else:
                st.session_state.cache_time = None
                progress_bar = st.progress(0)
                status_text = st.empty()

                raw_messages, total_checked, raw_fetched_at = load_raw_cache(channel_id)

                if raw_messages is not None and not force_reanalyze:
                    # 层级2：有原始数据缓存 → 跳过获取，直接排序+下载图片
                    status_text.text(f"使用原始数据缓存（{raw_fetched_at}），正在处理...")
                else:
                    # 层级3：都没有 → 从 Telegram 获取
                    raw_messages, total_checked, fetch_error = run_async(
                        fetch_messages_async(
                            selected_channel,
                            progress_bar,
                            status_text
                        )
                    )
                    if fetch_error:
                        st.error(fetch_error)
                        raw_messages = None

                    if raw_messages is not None:
                        save_raw_cache(channel_id, selected_channel['title'], raw_messages, total_checked)

                if raw_messages is not None:
                    progress_bar.progress(0)
                    results, proc_error = run_async(
                        process_results_async(
                            selected_channel,
                            raw_messages,
                            progress_bar,
                            status_text
                        )
                    )
                    if proc_error:
                        st.error(proc_error)
                    else:
                        save_cache(channel_id, selected_channel['title'], results)
                        st.session_state.results = results
                        st.session_state.selected_channel = selected_channel
                        st.session_state.cache_time = None
                        st.rerun()

        # 侧边栏 - 缓存管理（仅在选择了频道后显示）
        with st.sidebar:
            with st.expander("缓存管理"):
                if st.button("清除结果缓存", width="stretch"):
                    clear_result_cache(selected_channel['id'])
                    st.session_state.results = None
                    st.rerun()
                if st.button("清除所有缓存", width="stretch"):
                    clear_all_cache(selected_channel['id'])
                    st.session_state.results = None
                    st.rerun()

    # 显示分析结果
    if st.session_state.results is not None:
        results = st.session_state.results
        channel_title = st.session_state.selected_channel['title']

        cache_info = ""
        if st.session_state.get('cache_time'):
            cache_info = f"<p>使用缓存结果 · 分析时间: {st.session_state.cache_time}</p>"

        st.markdown(
            f'<div class="result-header">'
            f'<h2>分析结果: {html.escape(channel_title)}</h2>'
            f'{cache_info}'
            f'</div>',
            unsafe_allow_html=True,
        )

        if not results:
            st.warning("未找到任何有表情的消息")
        else:
            # 旧缓存兼容提示
            has_old_cache = any(msg.get('reaction_details') is None for msg in results)
            if has_old_cache:
                st.info("部分消息缺少表情明细数据（旧缓存），切换目标表情不会影响这些消息的统计值。建议勾选「忽略缓存」重新分析以获得完整数据。")

            # 关键词筛选
            keyword = st.session_state.get('keyword', '')
            if keyword:
                filtered = [m for m in results if keyword in (m.get('text') or '')]
                st.info(f"当前关键词筛选: 「{keyword}」，匹配 {len(filtered)} 条消息")
            else:
                filtered = results

            # 排序
            sort_method = st.session_state.get('sort_method', '目标表情数量')
            if sort_method == '热度':
                sorted_results = sorted(filtered, key=calc_hotness, reverse=True)
            else:
                sorted_results = sorted(filtered, key=lambda x: x['reactions'], reverse=True)

            # 统计汇总
            total_target = sum(m['reactions'] for m in filtered)
            total_all = sum(m['total_reactions'] for m in filtered)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("有表情的消息", len(filtered))
            col2.metric("目标表情总数", total_target)
            col3.metric("所有表情总数", total_all)
            if total_all > 0:
                col4.metric("目标表情占比", f"{total_target/total_all*100:.1f}%")

            # 结果展示
            sort_label = "热度" if sort_method == "热度" else "目标表情数量"
            st.markdown(f"### 排行榜（按{sort_label}排序）")

            for idx, msg in enumerate(sorted_results[:50], 1):
                image_path = msg.get('image_path')
                has_image = image_path and os.path.exists(image_path)

                badge_cls = "rank-badge top3" if idx <= 3 else "rank-badge"
                safe_text = html.escape(msg['text'] or '')
                views_fmt = f"{msg['views']:,}"
                forwards_fmt = f"{msg['forwards']:,}"

                hotness_stat = f'<span class="rank-stat primary">🔥 热度 {calc_hotness(msg):.2f}</span>' if sort_method == '热度' else ''

                card_html = (
                    f'<div class="rank-card">'
                    f'<span class="{badge_cls}">第 {idx} 名</span>'
                    f'<span style="color:#888; font-size:0.9em;">{html.escape(msg["date"])}</span>'
                    f'<div style="margin:10px 0;">{safe_text}</div>'
                    f'<div>'
                    f'{hotness_stat}'
                    f'<span class="rank-stat primary">目标表情 {msg["reactions"]}</span>'
                    f'<span class="rank-stat">总表情 {msg["total_reactions"]}</span>'
                    f'<span class="rank-stat">浏览 {views_fmt}</span>'
                    f'<span class="rank-stat">转发 {forwards_fmt}</span>'
                    f'</div>'
                    f'<div style="margin-top:8px;">'
                    f'<a href="{msg["link"]}" target="_blank" '
                    f'style="color:#0088cc; text-decoration:none; font-size:0.9em;">'
                    f'查看原文 &rarr;</a></div>'
                    f'</div>'
                )

                if has_image:
                    col_img, col_info = st.columns([1, 3])
                    with col_img:
                        st.image(image_path, width="stretch")
                    with col_info:
                        st.markdown(card_html, unsafe_allow_html=True)
                else:
                    st.markdown(card_html, unsafe_allow_html=True)

            # 导出报告
            st.markdown("---")
            st.markdown("### 导出报告")

            send_scope = st.radio(
                "发送范围",
                ["完整排行", "前 50 条"],
                horizontal=True,
            )

            if send_scope == "前 50 条":
                report_data = sorted_results[:50]
            else:
                report_data = sorted_results

            col_send, col_download = st.columns(2)

            with col_send:
                if st.button("发送到 Telegram 收藏", width="stretch"):
                    with st.spinner("正在发送到收藏夹..."):
                        ok, err = run_async(send_report_to_saved(report_data, channel_title))
                        if ok:
                            st.success("已发送到 Telegram 收藏夹")
                        else:
                            st.error(f"发送失败: {err}")

            with col_download:
                st.download_button(
                    label="下载完整报告",
                    data=generate_report(sorted_results, channel_title),
                    file_name=f"report_{channel_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    width="stretch",
                )


if __name__ == "__main__":
    main()
