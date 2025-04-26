import os
import sys
import json
import asyncio
import logging
import platform
import argparse
from datetime import datetime

from webhook import send_message_async

src_dir = os.path.join(os.path.dirname(__file__), 'src')
sys.path.append(src_dir)

# 导入自定义模块
from config import DATA_DIRS, BLOCKCHAIN_PLATFORMS, PLATFORMS_TO_QUERY
from src.utils.historical_data import BinanceAlphaDataCollector
from src.utils.binance_symbols import update_tokens, check_token_listing_status, prepare_token_listing_data
from src.ai import AlphaAdvisor

# 从新的AI模块导入DeepseekAdvisor
from src.ai.advisor import DeepseekAdvisor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('crypto_monitor.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

async def get_ai_investment_advice():
    """获取AI投资建议（使用DeepSeek R1模型）"""
    print("=== AI投资顾问 (DeepSeek R1) ===\n")
    
    # 检查是否存在整合后的数据
    data_file = "data/daily_data.json"
    if not os.path.exists(data_file):
        print("错误: 未找到整合后的数据文件，请先运行数据重组工具")
        return
    
    # 初始化AI顾问
    advisor = DeepseekAdvisor()
    
    # 设置分析月数和重试参数
    months = 6
    max_retries = 3
    retry_delay = 2.0
    
    print(f"将分析最近{months}个月的数据")
    print(f"已配置最大重试次数: {max_retries}，重试间隔: {retry_delay}秒")
    
    try:
        # 处理数据格式
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 如果数据是直接的列表(不是包含responses的字典)，包装成期望的格式
            if isinstance(data, list):
                print("注意: 正在准备数据格式以供AI处理...")
                wrapped_data = {"responses": data}
                
                # 创建临时文件
                temp_file = data_file + ".temp"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(wrapped_data, f, ensure_ascii=False, indent=2)
                
                # 使用临时文件代替原始文件
                data_file = temp_file
                print("数据格式已调整")
        except Exception as e:
            logger.warning(f"读取数据文件时出错: {str(e)}")
            print(f"警告: 读取数据文件时出错: {str(e)}，将继续尝试处理")
        
        # 获取投资建议
        print("\n正在获取AI投资建议，请稍候...\n")
        
        # 调用AI获取建议
        advice = advisor.get_investment_advice(
            data_file=data_file, 
            months=months, 
            max_retries=max_retries, 
            retry_delay=retry_delay,
            debug=True
        )
        
        if advice:
            print("\n成功获取AI投资建议:")
            print(advice)
            
            # 构建推送消息
            push_message = "🤖 AI投资顾问建议\n\n"
            push_message += f"{advice}"
            
            # 推送消息
            await send_message_async(push_message)
            return advice
        else:
            print("错误: 获取AI投资建议失败")
            print("可能原因: API服务器连接问题、API密钥无效或请求超时")
    
    except Exception as e:
        logger.error(f"AI投资建议处理过程中出错: {str(e)}")
        print(f"错误: {str(e)}")
        import traceback
        error_details = traceback.format_exc()
        logger.debug(error_details)
        print(f"错误详情已记录到日志文件")

async def get_binance_tokens():
    """获取Binance交易对列表并更新"""
    print("=== 更新Binance交易对列表 ===\n")
    
    try:
        # 更新token列表
        result = update_tokens()
        
        if result["symbols_changed"]:
            print(f"交易对列表已更新")
            print(f"已存在的token数量: {len(result['existing_tokens'])}")
            print(f"当前获取的token数量: {len(result['all_tokens'])}")
            print(f"新增token数量: {len(result['new_tokens'])}")
            
            if result['new_tokens']:
                print("新增token:")
                for token in result['new_tokens'][:10]:  # 只显示前10个
                    print(f"- {token}")
                if len(result['new_tokens']) > 10:
                    print(f"...以及其他 {len(result['new_tokens'])-10} 个token")
            else:
                print("没有新增的token")
        else:
            print("交易对列表未发生变化，使用现有token列表")
            print(f"现有token数量: {len(result['all_tokens'])}")
        
        # 打印CEX上线token的统计信息
        standard_tokens = result.get('standard_tokens', [])
        thousand_tokens = result.get('thousand_tokens', [])
        
        if standard_tokens or thousand_tokens:
            print(f"币安CEX上线的token数量: {len(standard_tokens) + len(thousand_tokens)}")
            print(f"其中标准形式token: {len(standard_tokens)}个")
            print(f"1000x形式token: {len(thousand_tokens)}个")
            
            # 打印部分信息
            if standard_tokens:
                print(f"前10个标准CEX token: {', '.join(sorted(standard_tokens)[:10])}")
                if len(standard_tokens) > 10:
                    print(f"...以及其他 {len(standard_tokens)-10} 个token")
            
            if thousand_tokens:
                print("1000Token形式:")
                for full_name, token_name in thousand_tokens[:5]:
                    print(f"- {full_name} (原始: {token_name})")
                if len(thousand_tokens) > 5:
                    print(f"...以及其他 {len(thousand_tokens)-5} 个")
            
            # 如果需要，可以推送CEX信息消息
            if result.get('cex_info_message'):
                print("\n币安现货上线Token信息已准备好，可用于推送")
        
        return result
    
    except Exception as e:
        logger.error(f"更新Binance交易对列表时出错: {str(e)}")
        print(f"错误: {str(e)}")
        import traceback
        error_details = traceback.format_exc()
        logger.debug(error_details)
        print(f"错误详情已记录到日志文件")
        return None

async def get_binance_alpha_list(force_update=False, listed_tokens=None):
    """获取币安Alpha项目列表数据并推送"""
    print("=== 币安Alpha项目列表数据 ===\n")
    
    # 创建数据目录
    os.makedirs(DATA_DIRS['data'], exist_ok=True)
    
    # 初始化币安Alpha数据收集器
    collector = BinanceAlphaDataCollector(data_dir=DATA_DIRS['data'])
    
    try:
        # 获取币安Alpha项目列表数据
        print("正在获取币安Alpha项目列表数据...")
        alpha_data = await collector.get_latest_data(force_update=force_update)
        
        if not alpha_data:
            logger.error("获取币安Alpha项目列表数据失败")
            print("错误: 获取币安Alpha项目列表数据失败")
            return False
        
        # 提取数据进行处理和展示
        crypto_list = alpha_data.get("data", {}).get("cryptoCurrencyList", [])
        total_count = alpha_data.get("total_count", 0)
        
        print(f"获取到{len(crypto_list)}个币安Alpha项目，CoinMarketCap显示总共有{total_count}个项目")
        
        # 如果提供了已上线Token列表，标记已上线的项目
        if listed_tokens:
            # 记录匹配到的已上线token
            matched_tokens = []
            matched_thousand_tokens = []
            
            # 为每个crypto添加isListed标记
            for crypto in crypto_list:
                symbol = crypto.get("symbol", "")
                if not symbol:
                    continue
                
                # 使用通用函数检查token上线状态
                status = check_token_listing_status(symbol, listed_tokens)
                
                # 添加isListed标记和listedAs信息
                crypto["isListed"] = status["is_listed"]
                if status["is_listed"]:
                    if status["listing_type"] == "standard":
                        matched_tokens.append(symbol)
                    elif status["listing_type"] == "1000x":
                        crypto["listedAs"] = status["listed_as"]
                        matched_thousand_tokens.append((symbol, status["listed_as"]))
            
            # 打印标记结果
            print(f"已标记{len(matched_tokens) + len(matched_thousand_tokens)}个已上线币安的Token")
            print(f"  - 标准形式: {len(matched_tokens)}个")
            print(f"  - 1000Token形式: {len(matched_thousand_tokens)}个")
            
            # 打印部分已标记的token
            if matched_tokens:
                print(f"标准形式已上线Token示例: {', '.join(matched_tokens[:5])}")
                if len(matched_tokens) > 5:
                    print(f"...以及其他 {len(matched_tokens)-5} 个")
            
            if matched_thousand_tokens:
                print("1000Token形式已上线Token示例:")
                for original, thousand in matched_thousand_tokens[:3]:
                    print(f"  - {original} (在币安上线为: {thousand})")
                if len(matched_thousand_tokens) > 3:
                    print(f"  ...以及其他 {len(matched_thousand_tokens)-3} 个")
        
        # 构建消息内容
        message = f"📊 币安Alpha项目列表 (更新时间: {alpha_data.get('date')})\n\n"
        message += f"🔢 项目总数: {total_count}\n\n"
        message += "🔝 Top 100 币安Alpha项目 (按市值排序):\n\n"
        
        # 添加前100个项目信息
        for i, crypto in enumerate(crypto_list[:100], 1):
            name = crypto.get("name", "未知")
            symbol = crypto.get("symbol", "未知")
            rank = crypto.get("cmcRank", "未知")
            price_usd = crypto.get("quotes", [{}])[2].get("price", 0) if len(crypto.get("quotes", [])) > 2 else 0
            percent_change_24h = crypto.get("quotes", [{}])[2].get("percentChange24h", 0) if len(crypto.get("quotes", [])) > 2 else 0
            market_cap = crypto.get("quotes", [{}])[2].get("marketCap", 0) if len(crypto.get("quotes", [])) > 2 else 0
            fdv = crypto.get("totalSupply", 0) * price_usd
            status = check_token_listing_status(symbol, listed_tokens)
            
            # 添加涨跌图标
            change_emoji = "🟢" if percent_change_24h >= 0 else "🔴"
            
            message += f"{i}. {name} ({symbol}) - 📈 CMC排名: {rank}\n"
            if status["is_listed"] == True:
                message += f"   🔔 已上线币安\n"
            
            message += f"   💰 价格: ${price_usd:.2f}, 24h变化: {change_emoji} {percent_change_24h:.2f}%\n"
            message += f"   💎 MC: ${market_cap/1000000:.2f}M, FDV: ${fdv/1000000:.2f}M\n"
        
        # 添加数据来源信息
        message += "📊 数据来源: CoinMarketCap\n"
        
        # 推送消息
        await send_message_async(message)
        
        print("\n币安Alpha项目列表数据已推送")
        return alpha_data  # 返回获取到的数据，以便后续处理
    
    except Exception as e:
        logger.error(f"获取币安Alpha项目列表数据过程中出错: {str(e)}")
        print(f"错误: {str(e)}")
        import traceback
        error_details = traceback.format_exc()
        logger.debug(error_details)
        print(f"错误详情已记录到日志文件")
        return False

async def classify_crypto_projects_by_platform(crypto_list, platforms, platforms_to_process):
    """
    对加密货币项目按照区块链平台进行分类，优先使用platform.name进行精确匹配
    
    Args:
        crypto_list: 加密货币项目列表
        platforms: 可用的区块链平台及其关键词字典
        platforms_to_process: 要处理的平台列表
        
    Returns:
        tuple: (平台项目字典, 未分类项目列表)
    """
    # 创建查找映射表，将具体平台名称映射到我们的目标平台类别
    platform_mapping = {
        "Ethereum": "Ethereum",
        "Solana": "Solana", 
        "BNB Smart Chain (BEP20)": "BNB Chain",  # 将BNB Smart Chain映射到BNB Chain
        "Base": "Other",  # 其他平台可以添加到此处
    }
    
    # 对项目按区块链平台分类
    platform_projects = {platform: [] for platform in platforms_to_process}
    unclassified_projects = []  # 记录无法分类的项目
    
    # 添加一个"Other"类别，用于收集不在指定平台列表中的项目
    if "Other" not in platform_projects and "Other" in platforms_to_process:
        platform_projects["Other"] = []
    
    for crypto in crypto_list:
        # 获取项目的平台信息
        platform_info = crypto.get("platform", {})
        platform_name = platform_info.get("name", "") if platform_info else ""
        
        # 获取标签中的生态系统信息，作为备选分类依据
        tags = [tag for tag in crypto.get("tags", []) if isinstance(tag, str)]
        ecosystem_tags = [tag for tag in tags if "ecosystem" in tag.lower()]
        
        # 初始化分配标志
        assigned = False
        
        # 通过platform.name直接匹配平台
        if platform_name and platform_name in platform_mapping:
            mapped_platform = platform_mapping[platform_name]
            
            # 检查映射的平台是否在我们要处理的平台中
            if mapped_platform in platforms_to_process:
                platform_projects[mapped_platform].append(crypto)
                assigned = True
            # 如果映射到了"Other"类别并且我们在处理该类别
            elif mapped_platform == "Other" and "Other" in platforms_to_process:
                platform_projects["Other"].append(crypto)
                assigned = True
        
        # 如果未通过platform.name匹配成功，尝试通过标签匹配
        if not assigned:
            for tag in ecosystem_tags:
                matched = False
                # 检查标签是否匹配平台
                for platform in platforms_to_process:
                    platform_keywords = platforms.get(platform, [])
                    # 使用简化的关键词匹配逻辑
                    if any(keyword.lower() in tag.lower() for keyword in platform_keywords):
                        platform_projects[platform].append(crypto)
                        assigned = True
                        matched = True
                        break
                
                if matched:
                    break
        
        # 如果仍然未分类，则添加到未分类列表
        if not assigned:
            unclassified_projects.append(crypto)
    
    # 打印分类结果
    print(f"币安Alpha项目分类统计：")
    total_classified = 0
    for platform, projects in platform_projects.items():
        print(f"{platform}: {len(projects)}个项目")
        total_classified += len(projects)
    print(f"未分类项目: {len(unclassified_projects)}个")
    print(f"总计: {total_classified + len(unclassified_projects)}个项目")
    
    return platform_projects, unclassified_projects

def determine_platforms_to_process(platforms, target_platform=None, debug_only=False):
    """
    确定要处理的平台列表
    
    Args:
        platforms: 可用的区块链平台字典
        target_platform: 指定要处理的平台（仅在调试模式下有效）
        debug_only: 是否为调试模式
        
    Returns:
        list: 要处理的平台列表
    """
    # 确定要处理的平台列表
    platforms_to_process = []
    
    # 如果命令行指定了特定平台且是调试模式，优先使用命令行指定的平台
    if target_platform and debug_only and target_platform in platforms:
        platforms_to_process = [target_platform]
    # 否则使用配置文件中的PLATFORMS_TO_QUERY
    elif PLATFORMS_TO_QUERY:
        # 确保只处理配置中存在的平台
        platforms_to_process = [p for p in PLATFORMS_TO_QUERY if p in platforms]
        if not platforms_to_process:
            logger.warning(f"配置的PLATFORMS_TO_QUERY中没有有效的平台: {PLATFORMS_TO_QUERY}")
            print(f"警告: 配置的平台{PLATFORMS_TO_QUERY}都不存在，将处理所有已定义的平台")
            platforms_to_process = list(platforms.keys())
    # 如果没有指定，则处理所有定义的平台
    else:
        platforms_to_process = list(platforms.keys())
        
    return platforms_to_process

async def get_alpha_investment_advice(alpha_data=None, debug_only=False, target_platform=None, listed_tokens=None):
    """获取基于当天币安Alpha数据的AI投资建议，按不同区块链平台分类
    
    Args:
        alpha_data: 币安Alpha数据
        debug_only: 是否仅生成提示词但不发送API请求（调试模式）
        target_platform: 指定要处理的平台（仅在调试模式下有效）
        listed_tokens: 已上线的Token列表，用于过滤掉不需要建议的项目
    """
    print("=== 币安Alpha项目AI投资建议 (按区块链平台分类) ===\n")
    if debug_only:
        print("【调试模式】仅生成提示词，不发送API请求\n")
        if target_platform:
            print(f"【仅处理】{target_platform}平台\n")
    
    try:
        # 初始化AI顾问
        advisor = AlphaAdvisor()
        
        # 设置重试参数
        max_retries = 3
        retry_delay = 2.0
        
        # 确认有Alpha数据
        if not alpha_data:
            logger.error("未提供币安Alpha数据，无法生成投资建议")
            print("错误: 未提供币安Alpha数据")
            return False
        
        # 提取项目列表
        crypto_list = alpha_data.get("data", {}).get("cryptoCurrencyList", [])
        date = alpha_data.get("date", "")
        
        if not crypto_list:
            logger.error("币安Alpha数据中未包含项目列表")
            print("错误: 币安Alpha数据中未包含项目列表")
            return False
        
        # 如果提供了已上线Token列表，过滤掉这些token
        if listed_tokens and listed_tokens.get('all_tokens'):
            original_count = len(crypto_list)
            
            # 过滤标准形式和1000Token形式的token
            filtered_crypto_list = []
            
            # 记录匹配到的token，用于日志输出
            matched_tokens = []
            matched_thousand_tokens = []
            
            for crypto in crypto_list:
                symbol = crypto.get("symbol", "")
                if not symbol:
                    filtered_crypto_list.append(crypto)  # 保留没有symbol的项目
                    continue
                
                # 使用通用函数检查token上线状态
                status = check_token_listing_status(symbol, listed_tokens)
                
                if not status["is_listed"]:
                    filtered_crypto_list.append(crypto)
                else:
                    # 记录已匹配的token
                    if status["listing_type"] == "standard":
                        matched_tokens.append(symbol)
                    elif status["listing_type"] == "1000x":
                        matched_thousand_tokens.append((symbol, status["listed_as"]))
            
            # 统计结果
            removed_count = original_count - len(filtered_crypto_list)
            
            # 打印详细过滤信息
            print(f"已从Alpha项目列表中移除{removed_count}个已上线的Token，剩余{len(filtered_crypto_list)}个项目")
            print(f"  - 标准形式Token移除: {len(matched_tokens)}个")
            print(f"  - 1000Token形式移除: {len(matched_thousand_tokens)}个")
            
            # 打印部分被过滤的token示例
            print(f"移除的标准Token: {', '.join(matched_tokens)}")
            
            if matched_thousand_tokens:
                print("移除的1000Token示例:")
                for original, thousand in matched_thousand_tokens[:3]:
                    print(f"  - {original} (对应1000形式: {thousand})")
                if len(matched_thousand_tokens) > 3:
                    print(f"  ...以及其他 {len(matched_thousand_tokens)-3} 个")
            
            crypto_list = filtered_crypto_list
            
            # 更新alpha_data中的项目列表
            alpha_data["data"]["cryptoCurrencyList"] = crypto_list
        
        # 使用配置中的区块链平台定义
        platforms = BLOCKCHAIN_PLATFORMS
        
        # 确定要处理的平台列表
        platforms_to_process = determine_platforms_to_process(platforms, target_platform, debug_only)
        print(f"将处理以下平台: {', '.join(platforms_to_process)}\n")
        
        # 对项目按区块链平台分类
        platform_projects, unclassified_projects = await classify_crypto_projects_by_platform(
            crypto_list, platforms, platforms_to_process
        )
        
        # 创建建议目录
        advice_dir = DATA_DIRS['advices']
        os.makedirs(advice_dir, exist_ok=True)
        
        # 按平台获取投资建议
        results = {}
        failed_platforms = []
        all_advice = f"# 币安Alpha项目投资建议 (按区块链平台分类，{date})\n\n"
        
        # 添加断路器计数
        consecutive_failures = 0
        max_consecutive_failures = 3
        
        for platform in platforms_to_process:
            projects = platform_projects.get(platform, [])
            
            # 跳过项目数量太少的平台
            if len(projects) < 5:
                message = f"跳过 {platform} 平台（项目数量: {len(projects)}）"
                logger.info(message)
                print(message)
                continue
                
            # 如果连续失败次数过多，激活断路器，跳过后续平台
            if consecutive_failures >= max_consecutive_failures:
                message = f"⚠️ 连续 {consecutive_failures} 次请求失败，跳过后续平台处理"
                logger.warning(message)
                print(message)
                failed_platforms.extend([p for p in platforms_to_process if p not in [platform for platform in results.keys()] + [platform for platform in failed_platforms]])
                break
            
            print(f"\n处理 {platform} 平台的 {len(projects)} 个项目...")
            
            # 为每个平台创建一个定制的alpha_data副本
            platform_alpha_data = {
                "date": date,
                "data": {"cryptoCurrencyList": projects},
                "total_count": len(projects),
                "platform": platform  # 添加平台信息
            }
            
            # 获取该平台的投资建议
            if os.getenv('DEEPSEEK_API_KEY') or debug_only:
                try:
                    platform_advice = advisor.get_investment_advice(
                        alpha_data=platform_alpha_data,
                        max_retries=max_retries,
                        retry_delay=retry_delay,
                        debug=True,
                        dry_run=debug_only
                    )
                    
                    if platform_advice:
                        results[platform] = platform_advice
                        consecutive_failures = 0  # 重置连续失败计数
                        
                        # 添加到全部建议中
                        all_advice += f"## {platform} 平台\n\n{platform_advice}\n\n"
                        
                        # 如果是调试模式，不发送消息到webhook
                        if not debug_only:
                            # 构建并推送该平台的消息
                            platform_message = f"🤖 币安Alpha {platform}平台项目AI投资建议\n\n"
                            platform_message += f"{platform_advice}"
                            
                            # 推送消息
                            await send_message_async(platform_message, msg_type="text")
                            logger.info(f"{platform} 平台投资建议已推送")
                        else:
                            print(f"{platform} 平台提示词已生成")
                        
                        # 文件保存已在advisor.get_investment_advice中处理
                    else:
                        logger.error(f"{platform} 平台生成投资建议失败")
                        failed_platforms.append(platform)
                        consecutive_failures += 1  # 增加连续失败计数
                except Exception as e:
                    logger.error(f"{platform} 平台生成投资建议过程中出错: {str(e)}")
                    failed_platforms.append(platform)
                    consecutive_failures += 1  # 增加连续失败计数
                    import traceback
                    error_details = traceback.format_exc()
                    logger.debug(error_details)
                
                # 添加延迟，避免API调用过于频繁（在非调试模式下）
                if not debug_only:
                    await asyncio.sleep(2)
            
        # 保存所有平台的综合建议到文件
        if results:
            # 获取当前时间戳用于文件命名
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            all_advice_file = f"{advice_dir}/advice_{timestamp}_all_platforms.md"
            with open(all_advice_file, "w", encoding="utf-8") as f:
                f.write(all_advice)
            
            logger.info(f"所有平台投资建议已保存到: {all_advice_file}")
            
            # 在非调试模式下推送综合建议
            if not debug_only:
                summary_message = "📊 币安Alpha项目投资建议 (按区块链平台分类)\n\n"
                summary_message += f"分析时间: {date}\n"
                summary_message += f"已分析平台: {', '.join(results.keys())}\n"
                
                if failed_platforms:
                    summary_message += f"\n处理失败平台: {', '.join(failed_platforms)}\n"
                
                summary_message += "\n各平台详细建议已单独发送，请查看。"
                
                await send_message_async(summary_message)
            
            # 打印成功/失败统计
            print(f"\n处理完成：")
            print(f"成功处理平台: {len(results)}个 - {', '.join(results.keys())}")
            if failed_platforms:
                print(f"处理失败平台: {len(failed_platforms)}个 - {', '.join(failed_platforms)}")
            
            return True if not failed_platforms else "partial_success"
        else:
            logger.error("没有生成任何平台的投资建议")
            return False
    
    except Exception as e:
        logger.error(f"生成币安Alpha项目投资建议过程中出错: {str(e)}")
        print(f"错误: {str(e)}")
        import traceback
        error_details = traceback.format_exc()
        logger.debug(error_details)
        print(f"错误详情已记录到日志文件")
        return False

async def main():
    """主函数
    
    执行流程:
    - 获取并更新Binance交易对列表
    - 获取币安Alpha项目列表数据
    - 按区块链平台分类项目
    - 为每个平台分别调用AI生成投资建议
    - 推送到webhook
    """
    
    # 从配置中获取支持的平台列表
    supported_platforms = list(BLOCKCHAIN_PLATFORMS.keys())
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Crypto Monitor - 币安Alpha项目分析工具")
    parser.add_argument("--debug-only", action="store_true", help="启用调试模式，仅生成提示词不发送API请求")
    parser.add_argument("--platform", type=str, choices=supported_platforms, 
                       help=f"指定要处理的平台（仅在调试模式下有效）: {', '.join(supported_platforms)}")
    parser.add_argument("--force-update", action="store_true", help="强制更新数据，不使用缓存")
    parser.add_argument("--skip-tokens-update", action="store_true", help="跳过更新Binance交易对列表")
    args = parser.parse_args()
    
    try:
        print("\n===============================================================")
        print(" 币安Alpha项目分析工具")
        print("===============================================================\n")
        
        # 显示运行模式信息
        print("运行模式:")
        mode_info = []
        
        if not args.skip_tokens_update:
            mode_info.append("- 获取并更新Binance交易对列表")
        
        mode_info.append("- 获取币安Alpha项目列表数据")
        
        if args.debug_only:
            mode_info.append("- 调试模式：仅生成提示词不发送API请求")
        else:
            mode_info.append("- 常规模式：生成投资建议并发送消息")
        
        if args.force_update:
            mode_info.append("- 强制更新：不使用缓存数据")
        
        for info in mode_info:
            print(info)
        print()
        
        # 获取并更新Binance交易对列表
        listed_tokens = None
        if not args.skip_tokens_update:
            print("步骤1: 获取并更新Binance交易对列表...\n")
            listed_tokens = await get_binance_tokens()
        
        # 获取币安Alpha项目列表数据
        step_num = 2 if not args.skip_tokens_update else 1
        print(f"步骤{step_num}: 获取币安Alpha项目列表数据...\n")
        alpha_data = await get_binance_alpha_list(force_update=args.force_update, listed_tokens=listed_tokens)
        if not alpha_data:
            logger.error("获取币安Alpha项目列表数据失败，程序退出")
            print("\n错误: 获取币安Alpha项目列表数据失败，程序退出")
            return 1
        
        step_num += 1
        print(f"\n步骤{step_num}: 分类项目并生成投资建议...\n")
        
        # 按区块链平台获取AI投资建议
        try:
            success = await get_alpha_investment_advice(
                alpha_data, 
                debug_only=args.debug_only, 
                target_platform=args.platform if args.debug_only else None,
                listed_tokens=listed_tokens
            )
            
            if success == True:
                if args.debug_only:
                    print("\n成功：提示词生成完成")
                else:
                    print("\n成功：所有平台投资建议处理完成")
            elif success == "partial_success":
                print("\n部分成功：某些平台处理成功，某些平台处理失败")
            else:
                print("\n警告：所有平台处理过程中出现错误")
        except Exception as e:
            logger.error(f"生成投资建议过程中出错: {str(e)}")
            print(f"\n错误: 生成投资建议过程中出错: {str(e)}")
            import traceback
            error_details = traceback.format_exc()
            logger.debug(error_details)
            print("错误详情已记录到日志文件")
            return 1
            
        print("\n===============================================================")
        print(" 处理完成，程序退出")
        print("===============================================================\n")
        return 0
        
    except Exception as e:
        logger.error(f"程序执行过程中出错: {str(e)}")
        print(f"\n错误: {str(e)}")
        import traceback
        error_details = traceback.format_exc()
        logger.debug(error_details)
        print("错误详情已记录到日志文件")
        return 1

if __name__ == "__main__":
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main()) 
