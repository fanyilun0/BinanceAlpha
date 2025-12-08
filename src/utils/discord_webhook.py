"""
Discord Webhook 发送模块

用于发送消息到 Discord 频道
"""

import aiohttp
import asyncio
import os
import sys

# 添加项目根目录到 sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import DISCORD_WEBHOOK_URL, PROXY_URL, USE_PROXY


def split_message(message: str, max_length: int = 2000) -> list[str]:
    """将长消息分割成多个片段
    
    Discord 单条消息限制 2000 字符
    
    Args:
        message: 要分割的消息
        max_length: 每个片段的最大长度
        
    Returns:
        消息片段列表
    """
    if len(message) <= max_length:
        return [message]
    
    segments = []
    lines = message.split('\n')
    current_segment = ""
    
    for line in lines:
        if len(current_segment) + len(line) + 1 > max_length:
            if current_segment:
                segments.append(current_segment.strip())
                current_segment = ""
            
            # 单行超长，强制分割
            if len(line) > max_length:
                while line:
                    segments.append(line[:max_length])
                    line = line[max_length:]
            else:
                current_segment = line
        else:
            if current_segment:
                current_segment += '\n'
            current_segment += line
    
    if current_segment:
        segments.append(current_segment.strip())
    
    # 添加片段序号
    total = len(segments)
    if total > 1:
        segments = [f"[{i+1}/{total}]\n{segment}" for i, segment in enumerate(segments)]
    
    return segments


async def _send_single_message(
    session: aiohttp.ClientSession,
    content: str,
    proxy: str | None,
    username: str | None = None
) -> bool:
    """发送单条消息到 Discord
    
    Args:
        session: aiohttp 会话
        content: 消息内容
        proxy: 代理设置
        username: 机器人显示名称
        
    Returns:
        是否发送成功
    """
    payload = {"content": content}
    if username:
        payload["username"] = username
    
    headers = {"Content-Type": "application/json"}
    
    try:
        async with session.post(
            DISCORD_WEBHOOK_URL, 
            json=payload, 
            headers=headers, 
            proxy=proxy
        ) as response:
            if response.status in (200, 204):
                print(f"Discord 消息发送成功! (长度: {len(content)})")
                return True
            else:
                text = await response.text()
                print(f"Discord 消息发送失败: {response.status}, {text}")
                return False
    except Exception as e:
        print(f"Discord 消息发送出错: {str(e)}")
        return False


async def _send_embed(
    session: aiohttp.ClientSession,
    embed: dict,
    proxy: str | None,
    username: str | None = None,
    content: str | None = None
) -> bool:
    """发送 Embed 消息到 Discord
    
    Args:
        session: aiohttp 会话
        embed: Embed 对象
        proxy: 代理设置
        username: 机器人显示名称
        content: 附加的普通文本内容
        
    Returns:
        是否发送成功
    """
    payload = {"embeds": [embed]}
    if username:
        payload["username"] = username
    if content:
        payload["content"] = content
    
    headers = {"Content-Type": "application/json"}
    
    try:
        async with session.post(
            DISCORD_WEBHOOK_URL, 
            json=payload, 
            headers=headers, 
            proxy=proxy
        ) as response:
            if response.status in (200, 204):
                print("Discord Embed 消息发送成功!")
                return True
            else:
                text = await response.text()
                print(f"Discord Embed 消息发送失败: {response.status}, {text}")
                return False
    except Exception as e:
        print(f"Discord Embed 消息发送出错: {str(e)}")
        return False


async def send_discord_message(
    message_content: str,
    username: str | None = "Binance Alpha Monitor"
) -> bool:
    """发送消息到 Discord webhook，支持长消息分段发送
    
    Args:
        message_content: 要发送的消息内容
        username: 机器人显示名称
        
    Returns:
        是否全部发送成功
    """
    if not DISCORD_WEBHOOK_URL:
        print("错误: DISCORD_WEBHOOK_URL 未配置")
        return False
    
    segments = split_message(message_content)
    total_segments = len(segments)
    
    if total_segments > 1:
        print(f"消息将被分成 {total_segments} 段发送")
    
    proxy = PROXY_URL if USE_PROXY else None
    
    async with aiohttp.ClientSession() as session:
        for i, segment in enumerate(segments):
            success = await _send_single_message(session, segment, proxy, username)
            
            if not success:
                print(f"第 {i+1}/{total_segments} 段消息发送失败")
                return False
            
            # 避免触发 Discord 频率限制
            if i < total_segments - 1:
                await asyncio.sleep(0.5)
    
    if total_segments > 1:
        print(f"所有 {total_segments} 段消息发送完成")
    
    return True


async def send_discord_embed(
    title: str,
    description: str,
    color: int = 0x5865F2,
    fields: list[dict] | None = None,
    footer: str | None = None,
    username: str | None = "Binance Alpha Monitor"
) -> bool:
    """发送 Embed 格式消息到 Discord
    
    Args:
        title: 标题
        description: 描述内容
        color: 颜色 (十六进制)
        fields: 字段列表 [{"name": "xxx", "value": "xxx", "inline": True/False}]
        footer: 页脚文本
        username: 机器人显示名称
        
    Returns:
        是否发送成功
    """
    if not DISCORD_WEBHOOK_URL:
        print("错误: DISCORD_WEBHOOK_URL 未配置")
        return False
    
    embed = {
        "title": title,
        "description": description,
        "color": color,
    }
    
    if fields:
        embed["fields"] = fields
    
    if footer:
        embed["footer"] = {"text": footer}
    
    proxy = PROXY_URL if USE_PROXY else None
    
    async with aiohttp.ClientSession() as session:
        return await _send_embed(session, embed, proxy, username)


# 颜色常量
class DiscordColors:
    """Discord Embed 颜色常量"""
    BLURPLE = 0x5865F2  # Discord 蓝紫色
    GREEN = 0x57F287    # 绿色 (成功/上涨)
    YELLOW = 0xFEE75C   # 黄色 (警告)
    RED = 0xED4245      # 红色 (错误/下跌)
    ORANGE = 0xE67E22   # 橙色
    PURPLE = 0x9B59B6   # 紫色
    BLUE = 0x3498DB     # 蓝色
    GREY = 0x95A5A6     # 灰色

