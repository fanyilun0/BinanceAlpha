import os
import sys
import json
import asyncio
import logging
import platform
from datetime import datetime

from webhook import send_message_async

src_dir = os.path.join(os.path.dirname(__file__), 'src')
sys.path.append(src_dir)

# 导入自定义模块
from config import DATA_DIRS
from src.utils.historical_data import BinanceAlphaDataCollector
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

async def get_binance_alpha_list():
    """获取币安Alpha项目列表数据并推送"""
    print("=== 币安Alpha项目列表数据 ===\n")
    
    # 创建数据目录
    os.makedirs(DATA_DIRS['data'], exist_ok=True)
    
    # 初始化币安Alpha数据收集器
    collector = BinanceAlphaDataCollector(data_dir=DATA_DIRS['data'])
    
    try:
        # 获取币安Alpha项目列表数据
        print("正在获取币安Alpha项目列表数据...")
        alpha_data = await collector.get_latest_data(force_update=True)
        
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

async def get_alpha_investment_advice(alpha_data=None):
    """获取基于当天币安Alpha数据的AI投资建议，按不同区块链平台分类"""
    print("=== 币安Alpha项目AI投资建议 (按区块链平台分类) ===\n")
    
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
        
        # 定义主要区块链平台
        platforms = {
            "Ethereum": ["ETH", "ERC20", "Ethereum", "ERC-20"],
            "Solana": ["SOL", "Solana", "SPL"], 
            "BNB Chain": ["BNB", "BSC", "BEP20", "BEP-20", "Binance Smart Chain"],
        }
        
        # 对项目按区块链平台分类
        platform_projects = {platform: [] for platform in platforms.keys()}
        
        for crypto in crypto_list:
            # 获取项目的平台信息
            platform_info = crypto.get("platform", {})
            platform_name = platform_info.get("name", "") if platform_info else ""
            platform_symbol = platform_info.get("symbol", "") if platform_info else ""
            
            # 尝试从tags或其他字段获取平台信息
            tags = crypto.get("tags", [])
            platform_tags = [tag for tag in tags if isinstance(tag, str)]
            
            # 判断项目所属平台
            assigned = False
            for platform, keywords in platforms.items():
                if any(keyword.lower() in platform_name.lower() for keyword in keywords) or \
                   any(keyword.lower() in platform_symbol.lower() for keyword in keywords) or \
                   any(any(keyword.lower() in tag.lower() for tag in platform_tags) for keyword in keywords):
                    platform_projects[platform].append(crypto)
                    assigned = True
                    break
            
            # 如果无法分类，放入"Other"
            if not assigned:
                platform_projects["Other"].append(crypto)
        
        # 打印分类结果
        print(f"币安Alpha项目分类统计：")
        for platform, projects in platform_projects.items():
            print(f"{platform}: {len(projects)}个项目")
        
        # 创建建议目录
        advice_dir = DATA_DIRS['advices']
        os.makedirs(advice_dir, exist_ok=True)
        
        # 按平台获取投资建议
        results = {}
        all_advice = f"# 币安Alpha项目投资建议 (按区块链平台分类，{date})\n\n"
        
        for platform, projects in platform_projects.items():
            # 跳过没有项目的平台
            if not projects:
                logger.info(f"跳过 {platform} 平台（无项目）")
                continue
                
            # 项目数量太少时也跳过
            if len(projects) < 5:
                logger.info(f"跳过 {platform} 平台（项目数量过少: {len(projects)}）")
                continue
            
            print(f"\n处理 {platform} 平台的 {len(projects)} 个项目...")
            
            # 为每个平台创建一个定制的alpha_data副本
            platform_alpha_data = {
                "date": date,
                "data": {"cryptoCurrencyList": projects},
                "total_count": len(projects)
            }
            
            # 获取该平台的投资建议
            if os.getenv('DEEPSEEK_API_KEY'):
                platform_advice = advisor.get_investment_advice(
                    alpha_data=platform_alpha_data,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    debug=True
                )
                
                if platform_advice:
                    results[platform] = platform_advice
                    
                    # 添加到全部建议中
                    all_advice += f"## {platform} 平台\n\n{platform_advice}\n\n"
                    
                    # 构建并推送该平台的消息
                    platform_message = f"🤖 币安Alpha {platform}平台项目AI投资建议\n\n"
                    platform_message += f"{platform_advice}"
                    
                    # 推送消息
                    await send_message_async(platform_message, msg_type="markdown")
                    logger.info(f"{platform} 平台投资建议已推送")
                    
                    # 单独保存该平台的建议到文件
                    platform_file = f"{advice_dir}/{platform.lower().replace(' ', '_')}_advice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                    with open(platform_file, "w", encoding="utf-8") as f:
                        f.write(platform_advice)
                    
                    logger.info(f"{platform} 平台投资建议已保存到: {platform_file}")
                else:
                    logger.error(f"{platform} 平台生成投资建议失败")
                    
                # 添加延迟，避免API调用过于频繁
                await asyncio.sleep(2)
            
        # 保存所有平台的综合建议到文件
        if results:
            all_advice_file = f"{advice_dir}/all_platforms_advice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            with open(all_advice_file, "w", encoding="utf-8") as f:
                f.write(all_advice)
            
            logger.info(f"所有平台投资建议已保存到: {all_advice_file}")
            
            # 推送综合建议
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
    - 获取币安Alpha项目列表数据
    - 按区块链平台分类项目
    - 为每个平台分别调用AI生成投资建议
    - 推送到webhook
    """
    
    try:
        print("模式: 币安Alpha项目列表数据和分平台AI投资建议\n")
        
        # 获取币安Alpha项目列表数据
        alpha_data = await get_binance_alpha_list()
        if not alpha_data:
            logger.error("获取币安Alpha项目列表数据失败，程序退出")
            return 1
            
        # 按区块链平台获取AI投资建议
        success = await get_alpha_investment_advice(alpha_data)
        
        if success:
            print("\n所有平台投资建议处理完成")
        else:
            print("\n平台投资建议生成过程中出现错误")
            
        print("\n处理完成，程序退出")
        return 0 if success else 1
        
    except Exception as e:
        logger.error(f"程序执行过程中出错: {str(e)}")
        print(f"错误: {str(e)}")
        return 1

if __name__ == "__main__":
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main()) 
