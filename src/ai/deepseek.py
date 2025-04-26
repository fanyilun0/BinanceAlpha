"""
DeepSeek API调用模块 - 提供与DeepSeek R1模型的API交互

此模块负责:
1. 提供统一的API调用接口
2. 管理身份验证和API密钥
3. 处理错误和异常情况
4. 格式化请求和响应
"""

import os
import json
import logging
import requests
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

# 导入配置
from config import DEEPSEEK_AI, DATA_DIRS

# 设置日志
logger = logging.getLogger(__name__)

class DeepseekAPI:
    """DeepSeek API接口类，提供与DeepSeek R1模型交互的方法"""
    
    def __init__(self, api_key: str = None, api_url: str = None):
        """初始化DeepSeek API客户端
        
        Args:
            api_key: DeepSeek API密钥，如果为None则尝试从环境变量获取
            api_url: 自定义API URL，如果为None则使用配置中的值
        """
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.api_url = api_url or DEEPSEEK_AI['api_url']
        
        if not self.api_key:
            logger.warning("未设置DeepSeek API密钥，请通过环境变量DEEPSEEK_API_KEY或初始化参数提供")
    
    def validate_api_key(self) -> bool:
        """验证API密钥是否设置
        
        Returns:
            如果API密钥已设置则返回True，否则返回False
        """
        return bool(self.api_key)
    
    def chat_completion(self, 
                        messages: List[Dict[str, str]], 
                        model: str = None,
                        temperature: float = None,
                        max_tokens: int = None,
                        top_p: float = None,
                        stream: bool = None,
                        max_retries: int = 3,
                        retry_delay: float = 2.0,
                        **kwargs) -> Optional[Dict[str, Any]]:
        """发送聊天补全请求至DeepSeek API
        
        Args:
            messages: 消息列表，格式为[{"role": "user", "content": "..."}, ...]
            model: 使用的模型名称，默认从配置读取
            temperature: 采样温度，控制输出的随机性，默认从配置读取
            max_tokens: 最大生成的token数量，默认从配置读取
            top_p: 核采样的概率质量，默认从配置读取
            stream: 是否使用流式响应，默认从配置读取
            max_retries: 最大重试次数
            retry_delay: 重试间隔时间（秒）
            **kwargs: 其他API参数
            
        Returns:
            API响应的JSON数据，如果调用失败则返回None
        """
        if not self.validate_api_key():
            logger.error("未设置API密钥，无法调用DeepSeek API")
            return None
        
        # 准备参数，优先使用传入的参数，否则使用配置中的默认值
        payload = {
            "model": model or DEEPSEEK_AI['model'],
            "messages": messages,
            "temperature": temperature if temperature is not None else DEEPSEEK_AI['temperature'],
            "max_tokens": max_tokens if max_tokens is not None else DEEPSEEK_AI['max_tokens'],
            "top_p": top_p if top_p is not None else DEEPSEEK_AI['top_p'],
            "stream": stream if stream is not None else DEEPSEEK_AI['stream']
        }
        
        # 添加其他可选参数
        payload.update(kwargs)
        
        # 调用API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # 实现重试逻辑
        retries = 0
        while retries <= max_retries:
            try:
                logger.info(f"正在调用DeepSeek API，模型: {payload['model']}，尝试次数: {retries + 1}/{max_retries + 1}")
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=DEEPSEEK_AI.get('timeout', 180))
                
                if response.status_code == 200:
                    logger.info("DeepSeek API调用成功")
                    return response.json()
                elif response.status_code == 429:  # 速率限制
                    logger.warning(f"API调用受到限制 (429)，等待重试...")
                    retries += 1
                    if retries <= max_retries:
                        # 等待时间指数增长
                        wait_time = retry_delay * (2 ** (retries - 1))
                        logger.info(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"达到最大重试次数，API调用失败: {response.status_code} - {response.text}")
                        return None
                elif response.status_code >= 500:  # 服务器错误
                    logger.warning(f"服务器错误 ({response.status_code})，尝试重试...")
                    retries += 1
                    if retries <= max_retries:
                        wait_time = retry_delay * (2 ** (retries - 1))
                        logger.info(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"达到最大重试次数，API调用失败: {response.status_code} - {response.text}")
                        return None
                else:
                    # 其他错误（如验证失败、参数错误等）不进行重试
                    logger.error(f"API调用失败: {response.status_code} - {response.text}")
                    return None
            
            except requests.exceptions.Timeout:
                logger.warning("API请求超时，尝试重试...")
                retries += 1
                if retries <= max_retries:
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    logger.error("达到最大重试次数，API请求超时")
                    return None
            except requests.exceptions.ConnectionError:
                logger.warning("API连接错误，尝试重试...")
                retries += 1
                if retries <= max_retries:
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    logger.error("达到最大重试次数，API连接失败")
                    return None
            except requests.exceptions.RequestException as e:
                # 其他requests异常
                logger.error(f"API请求异常: {str(e)}")
                retries += 1
                if retries <= max_retries:
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"达到最大重试次数，API请求失败: {str(e)}")
                    return None
            except Exception as e:
                logger.error(f"调用DeepSeek API出错: {str(e)}")
                retries += 1
                if retries <= max_retries:
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"达到最大重试次数，发生未知错误: {str(e)}")
                    return None
        
        return None
    
    def generate_text(self, prompt: str, max_retries: int = 3, retry_delay: float = 2.0, **kwargs) -> Optional[str]:
        """使用单一提示词生成文本响应
        
        这是chat_completion的简化版本，方便单个提示词的使用场景
        
        Args:
            prompt: 提示词文本
            max_retries: 最大重试次数
            retry_delay: 重试间隔时间（秒）
            **kwargs: 传递给chat_completion的其他参数
            
        Returns:
            生成的文本内容，如果调用失败则返回None
        """
        messages = [{"role": "user", "content": prompt}]
        response = self.chat_completion(messages, max_retries=max_retries, retry_delay=retry_delay, **kwargs)
        
        if response:
            
            self.save_response_to_file(response)
            
            try:
                content = response["choices"][0]["message"]["content"]
                return content
            except (KeyError, IndexError) as e:
                logger.error(f"解析API响应出错: {str(e)}")
                return None
        
        return None

    def save_response_to_file(self, response):
        """
        将AI回复保存到本地文件
        
        Args:
            response: AI的回复内容 (JSON对象)
        """
        try:
            # 创建保存目录
            responses_dir = os.path.join(DATA_DIRS['responses'])
            os.makedirs(responses_dir, exist_ok=True)
            
            # 生成带时间戳的文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"response_{timestamp}.json"
            file_path = os.path.join(responses_dir, filename)
            
            # 保存到文件 (作为JSON)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(response, f, ensure_ascii=False, indent=2)
                  
            logger.info(f"AI原始回复已保存至: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存AI回复时出错: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
