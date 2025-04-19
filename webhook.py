import aiohttp
import asyncio
from config import WEBHOOK_URL, PROXY_URL, USE_PROXY

async def _send_single_message(session, content, headers, proxy, msg_type="text"):
    """发送单条消息
    
    Args:
        session: aiohttp会话
        content: 消息内容
        headers: 请求头
        proxy: 代理设置
        msg_type: 消息类型，支持"text"和"markdown"
    """

    payload = {
        "msgtype": "text",
        "text": {
            "content": content
        }
    }
    
    try:
        async with session.post(WEBHOOK_URL, json=payload, headers=headers, proxy=proxy) as response:
            if response.status == 200:
                print(f"消息片段发送成功! (长度: {len(content)})")
                return True
            else:
                print(f"消息片段发送失败: {response.status}, {await response.text()}")
                return False
    except Exception as e:
        print(f"消息片段发送出错: {str(e)}")
        return False

def split_message(message, max_length=1000):
    """将长消息分割成多个片段
    
    Args:
        message (str): 要分割的消息
        max_length (int): 每个片段的最大长度
        
    Returns:
        list: 消息片段列表
    """
    # 如果消息长度在限制内，直接返回
    if len(message) <= max_length:
        return [message]
    
    segments = []
    lines = message.split('\n')
    current_segment = ""
    
    for line in lines:
        # 如果当前行加上当前片段的长度超过限制
        if len(current_segment) + len(line) + 1 > max_length:
            # 如果当前片段不为空，添加到片段列表
            if current_segment:
                segments.append(current_segment.strip())
                current_segment = ""
            
            # 如果单行超过最大长度，需要进一步分割
            if len(line) > max_length:
                while line:
                    segments.append(line[:max_length])
                    line = line[max_length:]
            else:
                current_segment = line
        else:
            # 添加换行符（除非是第一行）
            if current_segment:
                current_segment += '\n'
            current_segment += line
    
    # 添加最后一个片段
    if current_segment:
        segments.append(current_segment.strip())
    
    # 添加片段序号
    total = len(segments)
    segments = [f"[{i+1}/{total}]\n{segment}" for i, segment in enumerate(segments)]
    
    return segments

async def send_message_async(message_content, msg_type="text"):
    """发送消息到webhook，支持长消息分段发送
    
    Args:
        message_content (str): 要发送的消息内容
        msg_type (str): 消息类型，支持"text"和"markdown"
    """
    # 分割消息
    segments = split_message(message_content)
    total_segments = len(segments)
    
    if total_segments > 1:
        print(f"消息将被分成 {total_segments} 段发送")
    
    headers = {'Content-Type': 'application/json'}
    proxy = PROXY_URL if USE_PROXY else None
    
    async with aiohttp.ClientSession() as session:
        for i, segment in enumerate(segments):
            # 发送消息片段
            success = await _send_single_message(session, segment, headers, proxy, msg_type)
            
            if not success:
                print(f"第 {i+1}/{total_segments} 段消息发送失败")
                return
            
            # 如果不是最后一段，等待一小段时间以避免触发频率限制
            if i < total_segments - 1:
                await asyncio.sleep(0.5)  # 500ms 延迟
    
    if total_segments > 1:
        print(f"所有 {total_segments} 段消息发送完成")
    else:
        print("消息发送成功!")