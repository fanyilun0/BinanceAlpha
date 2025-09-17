import aiohttp
import asyncio
import base64
import os
import hashlib
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
    if msg_type == "text":
        payload = {
            "msgtype": "text",
            "text": {
                "content": content
            }
        }
    elif msg_type == "markdown":
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }
    else:
        print(f"不支持的消息类型: {msg_type}")
        return False
    
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
        
async def _send_image(session, image_path=None, image_base64=None, headers=None, proxy=None, title="图片"):
    """发送图片消息
    
    Args:
        session: aiohttp会话
        image_path: 图片路径
        image_base64: 图片base64编码，优先使用
        headers: 请求头
        proxy: 代理设置
        title: 图片标题
        
    Returns:
        bool: 是否发送成功
    """
    # 读取图片数据
    image_data = None
    
    # 优先使用已有的base64编码
    if image_base64:
        # 如果提供的是已编码的base64字符串，直接使用
        image_base64_str = image_base64
        # 将base64字符串解码为二进制数据用于计算MD5
        try:
            image_data = base64.b64decode(image_base64)
        except Exception as e:
            print(f"解码base64数据失败: {str(e)}")
            return False
    elif image_path:
        if not os.path.exists(image_path):
            print(f"图片不存在: {image_path}")
            return False
            
        # 读取图片并转换为base64
        with open(image_path, "rb") as img_file:
            image_data = img_file.read()
            image_base64_str = base64.b64encode(image_data).decode('utf-8')
    else:
        print("未提供图片数据")
        return False
    
    # 计算图片的MD5值
    md5_hash = hashlib.md5(image_data).hexdigest()
    
    # 构建图片消息，严格按照企业微信API要求格式
    payload = {
        "msgtype": "image",
        "image": {
            "base64": image_base64_str,
            "md5": md5_hash
        }
    }
    
    # 尝试发送
    try:
        async with session.post(WEBHOOK_URL, json=payload, headers=headers, proxy=proxy) as response:
            response_text = await response.text()
            if response.status == 200:
                response_json = await response.json()
                if response_json.get("errcode") == 0:
                    print(f"图片消息发送成功!")
                    return True
                else:
                    print(f"图片消息发送失败: 错误码 {response_json.get('errcode')}, 错误信息: {response_json.get('errmsg')}")
                    return False
            else:
                print(f"图片消息发送失败: 状态码 {response.status}, 响应: {response_text}")
                return False
    except Exception as e:
        print(f"图片消息发送出错: {str(e)}")
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

async def send_image_async(image_path=None, image_base64=None):
    """发送图片到webhook
    
    Args:
        image_path: 图片路径
        image_base64: 图片base64编码，优先使用
        
    Returns:
        bool: 是否发送成功
    """
    headers = {'Content-Type': 'application/json'}
    proxy = PROXY_URL if USE_PROXY else None
    
    async with aiohttp.ClientSession() as session:
        success = await _send_image(session, image_path, image_base64, headers, proxy)
        return success