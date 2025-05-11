import requests
import os
import json
from datetime import datetime
import re
import logging

# 设置日志
logger = logging.getLogger(__name__)

def fetch_symbols():
    """从Binance获取所有交易对"""
    response = requests.get('https://api.binance.com/api/v3/exchangeInfo')
    data = response.json()
    symbols = [s['symbol'] for s in data['symbols']]
    return symbols

def extract_token_names(symbols):
    """从交易对中提取通证(token)名称"""
    # 定义常见的计价货币
    quote_currencies = ['BTC', 'ETH', 'USDT', 'BUSD', 'BNB', 'USDC', 'EUR', 'TRY', 'FDUSD', 'TUSD', 'JPY', 'ARS', 'MXN', 'BRL', 'AEUR', 'PLN', 'RUB', 'RON', 'VAI', 'EURI', 'CZK', 'COP']
    
    # 添加一些已知的特殊情况
    special_cases = {
        'BTCDOMUSDT': 'BTCDOM',  # 比特币主导地位指数
        'BTCDOMBUSD': 'BTCDOM',
        'DEFIUSDT': 'DEFI',      # DeFi指数
        'DEFIBUSD': 'DEFI',
        # 可以根据实际情况添加更多特殊情况
    }
    
    tokens = set()
    unmatched_symbols = []
    
    # 首先处理特殊情况
    for symbol in symbols:
        if symbol in special_cases:
            tokens.add(special_cases[symbol])
            continue
    
        # 尝试使用常规方法提取token名称
        matched = False
        for quote in quote_currencies:
            if symbol.endswith(quote):
                token = symbol[:-len(quote)]
                if token and re.match(r'^[A-Z0-9]+$', token):  # 确保token只包含大写字母和数字
                    tokens.add(token)
                    matched = True
                    break
        
        # 如果没有匹配到，记录下来供后续处理
        if not matched:
            unmatched_symbols.append(symbol)
    
    # 处理未匹配的交易对
    if unmatched_symbols:
        logger.info(f"发现{len(unmatched_symbols)}个未匹配的交易对：{', '.join(unmatched_symbols[:10])}" + 
                   (f"...等共{len(unmatched_symbols)}个" if len(unmatched_symbols) > 10 else ""))
        
        # 尝试更复杂的提取方法
        for symbol in unmatched_symbols:
            # 检查是否符合基本格式要求
            if re.match(r'^[A-Z0-9]+$', symbol):
                # 尝试将symbol本身作为token添加（如果它不是计价货币）
                if symbol not in quote_currencies:
                    tokens.add(symbol)
                
                # 处理类似1000TOKEN形式的token
                number_token_match = re.match(r'^(\d+)([A-Z]+)$', symbol)
                if number_token_match:
                    token_name = number_token_match.group(2)
                    if token_name not in quote_currencies:
                        tokens.add(token_name)
            
            # 这里可以添加更多复杂的提取规则
            # 例如针对TOKEN1TOKEN2这种情况的处理
    
    return sorted(list(tokens))

def get_existing_tokens():
    """获取已存在的token列表"""
    # 获取项目根目录
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    symbols_dir = os.path.join(root_dir, 'symbols')
    
    # 创建symbols目录（如果不存在）
    if not os.path.exists(symbols_dir):
        os.makedirs(symbols_dir)
        return []
    
    # 获取已有的symbols文件列表
    symbol_files = [f for f in os.listdir(symbols_dir) if os.path.isfile(os.path.join(symbols_dir, f)) and f.endswith('.json')]
    if not symbol_files:
        return []
    
    # 读取最新的symbols文件
    latest_file = sorted(symbol_files)[-1]
    with open(os.path.join(symbols_dir, latest_file), 'r') as f:
        existing_tokens = json.load(f)
    
    return existing_tokens

def get_raw_symbols_file():
    """获取最新的原始symbols文件路径，如果不存在则返回None"""
    # 获取项目根目录
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    symbols_dir = os.path.join(root_dir, 'symbols', 'raw')
    
    # 如果目录不存在，返回None
    if not os.path.exists(symbols_dir):
        return None
    
    # 获取所有的raw symbols文件
    symbol_files = [f for f in os.listdir(symbols_dir) if os.path.isfile(os.path.join(symbols_dir, f)) and f.endswith('.json')]
    if not symbol_files:
        return None
    
    # 返回最新的文件路径
    latest_file = sorted(symbol_files)[-1]
    return os.path.join(symbols_dir, latest_file)

def get_cex_tokens():
    """获取币安CEX上已上线的token"""
    try:
        # 获取所有交易对
        symbols = fetch_symbols()
        
        # 提取token名称
        cex_tokens = extract_token_names(symbols)
        
        logger.info(f"从币安获取到{len(cex_tokens)}个上线token")
        return cex_tokens
    except Exception as e:
        logger.error(f"获取币安CEX上线token时出错: {str(e)}")
        # 出错时返回空列表
        return []

def check_token_listing_status(token, listed_tokens=None):
    """检查token是否已经在币安现货上线
    
    Args:
        token (str): 要检查的token符号
        listed_tokens (dict, optional): 已获取的上线token信息字典，如果为None则重新获取
    
    Returns:
        dict: 包含以下信息的字典：
            - is_listed (bool): 是否已上线
            - listing_type (str, optional): 上线类型，'standard'或'1000x'或None
            - listed_as (str, optional): 实际上线的符号名称
    """
    # 确保token是大写
    token = token.upper() if token else ""
    
    if not token:
        return {"is_listed": False}
    
    # 如果没有提供listed_tokens，则获取最新数据
    if not listed_tokens:
        try:
            listed_tokens_data = update_tokens()
            if not listed_tokens_data:
                logger.warning("获取上线token列表失败")
                return {"is_listed": False}
        except Exception as e:
            logger.error(f"检查token上线状态时出错: {str(e)}")
            return {"is_listed": False}
    else:
        listed_tokens_data = listed_tokens
    
    # 获取标准形式的token集合（不区分大小写）
    standard_tokens_set = {t.upper() for t in listed_tokens_data.get('standard_tokens', [])}
    if not standard_tokens_set and 'all_tokens' in listed_tokens_data:
        # 如果没有专门的standard_tokens，使用all_tokens
        standard_tokens_set = {t.upper() for t in listed_tokens_data.get('all_tokens', [])}
    
    # 获取1000Token形式的映射
    thousand_tokens = listed_tokens_data.get('thousand_tokens', [])
    thousand_tokens_map = {real_token.upper(): full_name.upper() 
                         for full_name, real_token in thousand_tokens}
    
    # 检查是否是标准形式token
    if token in standard_tokens_set:
        return {
            "is_listed": True,
            "listing_type": "standard",
            "listed_as": token
        }
    
    # 检查是否是1000Token对应的代币
    elif token in thousand_tokens_map:
        return {
            "is_listed": True,
            "listing_type": "1000x",
            "listed_as": thousand_tokens_map[token]
        }
    
    return {"is_listed": False}

def prepare_token_listing_data(tokens_data):
    """预处理币安上线token数据，分离标准token和1000x形式token
    
    Args:
        tokens_data (dict): update_tokens()返回的token数据
    
    Returns:
        dict: 包含以下字段的字典：
            - standard_tokens (list): 标准形式的token列表
            - thousand_tokens (list): 1000x形式的token元组列表，每个元组为(full_name, real_token)
            - cex_info_message (str): 格式化的CEX上线信息
    """
    if not tokens_data or not isinstance(tokens_data, dict):
        logger.warning("无效的token数据")
        return {
            "standard_tokens": [],
            "thousand_tokens": [],
            "cex_info_message": "无有效数据"
        }
    
    # 获取CEX上线的token列表
    cex_tokens = tokens_data.get('cex_tokens', [])
    if cex_tokens is None:
        cex_tokens = []
        logger.warning("cex_tokens为None，使用空列表代替")
    
    # 预处理1000Token形式的代币名称
    thousand_tokens = []
    standard_tokens = []
    
    for token in cex_tokens:
        if token.startswith('1000') and len(token) > 4:
            # 提取1000后面的实际代币名称
            real_token = token[4:]
            thousand_tokens.append((token, real_token))  # 保存元组(完整名称, 实际代币名称)
        else:
            standard_tokens.append(token)
    
    # 构建上线信息消息
    cex_info = "🔔 币安现货已上线Token列表：\n\n"
    
    # 添加常规token
    if standard_tokens:
        cex_info += "📊 标准Token：\n"
        for i, token in enumerate(sorted(standard_tokens)[:20], 1):
            cex_info += f"{i}. {token}\n"
        if len(standard_tokens) > 20:
            cex_info += f"...以及其他 {len(standard_tokens)-20} 个token\n"
        cex_info += "\n"
    
    # 添加1000Token形式的信息
    if thousand_tokens:
        cex_info += "💰 1000Token形式：\n"
        for i, (full_name, token_name) in enumerate(sorted(thousand_tokens), 1):
            cex_info += f"{i}. {full_name} (原始: {token_name})\n"
        cex_info += "\n"
    
    return {
        "standard_tokens": standard_tokens,
        "thousand_tokens": thousand_tokens,
        "cex_info_message": cex_info
    }

def update_tokens():
    """更新token列表并返回新token，只有在交易对列表变化时才保存"""
    # 获取项目根目录
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    symbols_dir = os.path.join(root_dir, 'symbols')
    raw_symbols_dir = os.path.join(symbols_dir, 'raw')
    
    # 确保目录存在
    if not os.path.exists(symbols_dir):
        os.makedirs(symbols_dir)
    if not os.path.exists(raw_symbols_dir):
        os.makedirs(raw_symbols_dir)
    
    # 获取当前日期和时间
    current_datetime = datetime.now().strftime('%Y%m%d-%H%M%S')
    
    # 获取现有的tokens
    existing_tokens = get_existing_tokens()
    
    # 获取所有交易对
    all_symbols = fetch_symbols()
    
    # 检查交易对列表是否有变化
    symbols_changed = True
    latest_raw_file = get_raw_symbols_file()
    
    if latest_raw_file:
        try:
            with open(latest_raw_file, 'r') as f:
                previous_symbols = json.load(f)
            
            # 比较新旧交易对列表
            if set(all_symbols) == set(previous_symbols):
                symbols_changed = False
                logger.info("交易对列表未发生变化，使用已有token列表")
        except Exception as e:
            logger.warning(f"读取上一次的交易对列表时出错: {str(e)}，将重新保存")
    
    # 如果交易对列表有变化，保存原始数据和提取的token
    if symbols_changed:
        # 保存原始交易对列表
        raw_filename = f"raw-symbols-{current_datetime}.json"
        raw_filepath = os.path.join(raw_symbols_dir, raw_filename)
        with open(raw_filepath, 'w') as f:
            json.dump(all_symbols, f, indent=2)
        
        # 提取token名称
        token_names = extract_token_names(all_symbols)
        
        # 保存提取的token列表
        filename = f"symbol.json"
        filepath = os.path.join(symbols_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(token_names, f, indent=2)
        
        # 找出新增的token（不在已存在列表中的）
        new_tokens = [t for t in token_names if t not in existing_tokens]
        
        # 获取CEX上线的token
        cex_tokens = get_cex_tokens()
        
        # 预处理token数据
        token_data = prepare_token_listing_data({"cex_tokens": cex_tokens})
        
        return {
            "all_tokens": token_names,
            "new_tokens": new_tokens,
            "existing_tokens": existing_tokens,
            "cex_tokens": cex_tokens,
            "standard_tokens": token_data["standard_tokens"],
            "thousand_tokens": token_data["thousand_tokens"],
            "cex_info_message": token_data["cex_info_message"],
            "file_path": filepath,
            "symbols_changed": True
        }
    else:
        # 如果交易对列表没有变化，返回已有的token列表
        # 即使交易对列表没变，也要获取最新的CEX上线token
        cex_tokens = get_cex_tokens()
        
        # 预处理token数据
        token_data = prepare_token_listing_data({"cex_tokens": cex_tokens})
        
        return {
            "all_tokens": existing_tokens,
            "new_tokens": [],
            "existing_tokens": existing_tokens,
            "cex_tokens": cex_tokens,
            "standard_tokens": token_data["standard_tokens"],
            "thousand_tokens": token_data["thousand_tokens"],
            "cex_info_message": token_data["cex_info_message"],
            "file_path": latest_raw_file,
            "symbols_changed": False
        }

def is_token_listed(symbol: str, symbol_list_path: str = None) -> bool:
    """
    检查token是否已在币安上线，通过直接读取symbol.json文件
    
    Args:
        symbol: 要检查的token符号
        symbol_list_path: symbol.json文件路径，如果为None则使用默认路径
        
    Returns:
        bool: 是否已上线
    """
    # 确保symbol是大写
    symbol = symbol.upper() if symbol else ""
    
    if not symbol:
        return False
        
    # 如果没有指定路径，使用默认路径
    if not symbol_list_path:
        # 获取项目根目录的symbols目录
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        symbol_list_path = os.path.join(root_dir, 'symbols', 'symbol.json')
    
    try:
        # 读取symbol.json文件
        with open(symbol_list_path, 'r') as f:
            listed_tokens = json.load(f)
            
        # 检查标准形式token
        if symbol in listed_tokens:
            return True
            
        # 检查1000x形式token
        for token in listed_tokens:
            if token.startswith('1000') and token[4:] == symbol:
                return True
                
        return False
        
    except Exception as e:
        print(f"检查token上线状态时出错: {str(e)}")
        return False

if __name__ == "__main__":
    # 当作为独立脚本运行时执行的代码
    result = update_tokens()
    
    if result["symbols_changed"]:
        print(f"交易对列表已更新")
        print(f"已存在的token数量: {len(result['existing_tokens'])}")
        print(f"提取出的token数量: {len(result['all_tokens'])}")
        print(f"所有token已保存到: {result['file_path']}")
        print(f"新增token数量: {len(result['new_tokens'])}")
        
        if result['new_tokens']:
            print("新增token:")
            print(json.dumps(result['new_tokens'], indent=2))
        else:
            print("没有新增的token")
    else:
        print("交易对列表未发生变化，无需更新token列表")
        print(f"现有token数量: {len(result['all_tokens'])}") 