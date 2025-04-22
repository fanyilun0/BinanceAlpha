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
from src.utils.binance_symbols import update_tokens
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
            
        return result
    
    except Exception as e:
        logger.error(f"更新Binance交易对列表时出错: {str(e)}")
        print(f"错误: {str(e)}")
        import traceback
        error_details = traceback.format_exc()
        logger.debug(error_details)
        print(f"错误详情已记录到日志文件")
        return None

async def get_binance_alpha_list(force_update=False):
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
        
        # 构建消息内容
        message = f"📊 币安Alpha项目列表 (更新时间: {alpha_data.get('date')})\n\n"
        message += f"项目总数: {total_count}\n\n"
        message += "🔝 Top 20 币安Alpha项目 (按市值排序):\n\n"
        
        # 添加前20个项目信息
        for i, crypto in enumerate(crypto_list[:20], 1):
            name = crypto.get("name", "未知")
            symbol = crypto.get("symbol", "未知")
            rank = crypto.get("cmcRank", "未知")
            price_usd = crypto.get("quotes", [{}])[2].get("price", 0) if len(crypto.get("quotes", [])) > 2 else 0
            percent_change_24h = crypto.get("quotes", [{}])[2].get("percentChange24h", 0) if len(crypto.get("quotes", [])) > 2 else 0
            market_cap = crypto.get("quotes", [{}])[2].get("marketCap", 0) if len(crypto.get("quotes", [])) > 2 else 0
            fdv = crypto.get("totalSupply", 0) * price_usd
            message += f"{i}. {name} ({symbol}) - CMC排名: {rank}\n"
            message += f"   价格: ${price_usd:.6f}, 24h变化: {percent_change_24h:.2f}%\n"
            message += f"   市值: ${market_cap:.2f}, 完全稀释估值: ${fdv:.2f}\n"
        
        # 添加数据来源信息
        message += "数据来源: CoinMarketCap\n"
        
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
            
            # 创建一个已上线token的集合，不区分大小写，便于比较
            listed_tokens_set = {token.upper() for token in listed_tokens.get('all_tokens')}
            
            # 过滤掉已经上线的token
            filtered_crypto_list = [
                crypto for crypto in crypto_list 
                if crypto.get("symbol", "").upper() not in listed_tokens_set
            ]
            
            removed_count = original_count - len(filtered_crypto_list)
            print(f"已从Alpha项目列表中移除{removed_count}个已上线的Token，剩余{len(filtered_crypto_list)}个项目")
            crypto_list = filtered_crypto_list
            
            # 更新alpha_data中的项目列表
            alpha_data["data"]["cryptoCurrencyList"] = crypto_list
        
        # 使用配置中的区块链平台定义
        platforms = BLOCKCHAIN_PLATFORMS
        
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
            
        print(f"将处理以下平台: {', '.join(platforms_to_process)}\n")
        
        # 对项目按区块链平台分类
        platform_projects = {platform: [] for platform in platforms_to_process}
        unclassified_projects = []  # 记录无法分类的项目
        
        for crypto in crypto_list:
            # 获取项目的各种可能包含平台信息的字段
            platform_info = crypto.get("platform", {})
            platform_name = platform_info.get("name", "") if platform_info else ""
            platform_symbol = platform_info.get("symbol", "") if platform_info else ""
            tags = crypto.get("tags", [])
            category = crypto.get("category", "")
            description = crypto.get("description", "")
            
            # 扁平化标签列表，确保是字符串
            platform_tags = [tag for tag in tags if isinstance(tag, str)]
            
            # 判断项目所属平台
            assigned = False
            
            # 仅对要处理的平台进行分类
            for platform in platforms_to_process:
                keywords = platforms[platform]
                # 检查各种字段中是否包含平台关键词
                if (any(keyword.lower() in platform_name.lower() for keyword in keywords) or
                    any(keyword.lower() in platform_symbol.lower() for keyword in keywords) or
                    any(any(keyword.lower() in tag.lower() for tag in platform_tags) for keyword in keywords) or
                    any(keyword.lower() in category.lower() for keyword in keywords) or
                    any(keyword.lower() in description.lower() for keyword in keywords)):
                    platform_projects[platform].append(crypto)
                    assigned = True
                    break
            
            # 记录无法分类的项目（不处理）
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
        
        # 创建建议目录
        advice_dir = DATA_DIRS['advices']
        os.makedirs(advice_dir, exist_ok=True)
        
        # 按平台获取投资建议
        results = {}
        all_advice = f"# 币安Alpha项目投资建议 (按区块链平台分类，{date})\n\n"
        
        for platform in platforms_to_process:
            projects = platform_projects.get(platform, [])
            
            # 跳过项目数量太少的平台
            if len(projects) < 5:
                message = f"跳过 {platform} 平台（项目数量: {len(projects)}）"
                logger.info(message)
                print(message)
                continue
            
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
                platform_advice = advisor.get_investment_advice(
                    alpha_data=platform_alpha_data,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    debug=True,
                    dry_run=debug_only
                )
                
                if platform_advice:
                    results[platform] = platform_advice
                    
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
                summary_message += f"已分析平台: {', '.join(results.keys())}\n\n"
                summary_message += "各平台详细建议已单独发送，请查看。"
                
                await send_message_async(summary_message)
            
            return True
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
            print()  # 添加空行，提高可读性
        
        # 获取币安Alpha项目列表数据
        step_num = 2 if not args.skip_tokens_update else 1
        print(f"步骤{step_num}: 获取币安Alpha项目列表数据...\n")
        alpha_data = await get_binance_alpha_list(force_update=args.force_update)
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
            
            if success:
                if args.debug_only:
                    print("\n成功：提示词生成完成")
                else:
                    print("\n成功：所有平台投资建议处理完成")
            else:
                print("\n警告：部分平台处理过程中出现错误")
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
