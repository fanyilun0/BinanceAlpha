import os
import sys
import json
import asyncio
import logging
import platform
import argparse
import time
from datetime import datetime

from webhook import send_message_async

src_dir = os.path.join(os.path.dirname(__file__), 'src')
sys.path.append(src_dir)

# 导入自定义模块
from config import DATA_DIRS, BLOCKCHAIN_PLATFORMS, PLATFORMS_TO_QUERY
from src.utils.historical_data import BinanceAlphaDataCollector
from src.utils.binance_symbols import is_token_listed, update_tokens, check_token_listing_status
from src.utils.crypto_formatter import format_project_summary, save_crypto_list_by_platform, save_crypto_data
from src.ai import AlphaAdvisor
from src.utils.image_generator import (
    create_alpha_table_image, 
    create_top_vol_mc_ratio_image,
    create_gainers_losers_image
)


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

async def send_alpha_rank_image(crypto_list, date, debug_only=False, max_items=100):
    """生成并发送按排名排序的Alpha项目图片
    
    Args:
        crypto_list: 加密货币项目列表
        date: 数据日期
        debug_only: 是否仅调试模式
        max_items: 最大显示项目数
        
    Returns:
        Tuple[str, str]: 图片路径和base64编码
    """
    print(f"准备生成按排名排序的Alpha项目图片...")
    
    # 创建图片表格
    image_path, image_base64 = create_alpha_table_image(
        crypto_list=crypto_list, 
        date=date,
        max_items=max_items
    )
    
    # 发送图片消息
    # print(f"准备发送按排名排序的图片到webhook...")
    
    # if not debug_only:
    #     from webhook import send_image_async
    #     await send_image_async(
    #         image_path=image_path, 
    #         image_base64=image_base64,
    #     )
    #     print("按排名排序的图片已成功发送到webhook")
    # else:
    #     print("Debug模式：跳过发送按排名排序的图片")
    
    return image_path, image_base64

async def send_alpha_liquidity_image(crypto_list, date, debug_only=False, max_items=100):
    """生成并发送按流动性（VOL/MC比值）排序的Top{max_items}项目图片
    
    Args:
        crypto_list: 加密货币项目列表
        date: 数据日期
        debug_only: 是否仅调试模式
        
    Returns:
        Tuple[str, str]: 图片路径和base64编码
    """
    print(f"准备生成按流动性排序的Top{max_items}项目图片...")
    
    image_path, image_base64 = create_top_vol_mc_ratio_image(
        crypto_list=crypto_list,
        date=date,
        max_items=max_items
    )
    
    # print(f"准备发送按流动性排序的图片到webhook...")
    
    # if not debug_only:
    #     from webhook import send_image_async
    #     await send_image_async(
    #         image_path=image_path,
    #         image_base64=image_base64,
    #     )
    #     print("按流动性排序的图片已成功发送到webhook")
    # else:
    #     print("Debug模式：跳过发送按流动性排序的图片")
    
    return image_path, image_base64

async def send_alpha_gainers_losers_image(crypto_list, date, debug_only=False, max_items=100):
    """生成并发送涨跌幅榜图片（合并涨幅和跌幅，按涨跌幅从高到低排序）
    
    Args:
        crypto_list: 加密货币项目列表
        date: 数据日期
        debug_only: 是否仅调试模式
        max_items: 最大显示项目数
        
    Returns:
        Tuple[str, str]: 图片路径和base64编码
    """
    print(f"准备生成涨跌幅榜图片（Top{max_items}，按涨跌幅排序）...")
    
    # 创建涨跌幅榜图片
    image_path, image_base64 = create_gainers_losers_image(
        crypto_list=crypto_list,
        date=date,
        max_items=max_items
    )
    
    # print(f"准备发送涨跌幅榜图片到webhook...")
    
    # if not debug_only:
    #     from webhook import send_image_async
    #     await send_image_async(
    #         image_path=image_path,
    #         image_base64=image_base64,
    #     )
    #     print("涨跌幅榜图片已成功发送到webhook")
    # else:
    #     print("Debug模式：跳过发送涨跌幅榜图片")
    
    return image_path, image_base64

async def send_alpha_image(crypto_list, date, debug_only=False, max_items=100):
    await send_alpha_rank_image(
        crypto_list=crypto_list,
        date=date,
        debug_only=debug_only,
        max_items=max_items
    )
    await send_alpha_liquidity_image(
        crypto_list=crypto_list,
        date=date,
        debug_only=debug_only,
        max_items=max_items
    )
    await send_alpha_gainers_losers_image(
        crypto_list=crypto_list,
        date=date,
        debug_only=debug_only,
        max_items=max_items
    )


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

async def get_binance_alpha_list(listed_tokens=None, debug_only=False):
    """获取币安Alpha项目列表数据并推送
    
    Args:
        listed_tokens: 已上线币安的token列表
        debug_only: 是否仅调试（不推送）
    
    Returns:
        获取的Alpha数据或失败时返回False
    """
    print("=== 币安Alpha项目列表数据 ===\n")
    
    # 创建数据目录
    os.makedirs(DATA_DIRS['data'], exist_ok=True)
    
    # 初始化币安Alpha数据收集器
    collector = BinanceAlphaDataCollector(data_dir=DATA_DIRS['data'])
    
    try:
        # 获取币安Alpha项目列表数据
        print("正在获取币安Alpha项目列表数据...")
        alpha_data = await collector.get_latest_data()
        
        if not alpha_data:
            logger.error("获取币安Alpha项目列表数据失败")
            print("错误: 获取币安Alpha项目列表数据失败")
            return False
        
        # 提取数据进行处理和展示
        crypto_list = alpha_data.get("data", {}).get("cryptoCurrencyList", [])
        total_count = alpha_data.get("total_count", 0)
        
        print(f"获取到{len(crypto_list)}个币安Alpha项目，CoinMarketCap显示总共有{total_count}个项目")
        
        # 检查币安已上线项目
        if listed_tokens and listed_tokens.get('all_tokens'):
            # 统计已上线的项目
            already_listed_tokens = []
            
            for crypto in crypto_list:
                symbol = crypto.get("symbol", "")
                if not symbol:
                    continue
                
                if is_token_listed(symbol):
                    already_listed_tokens.append(symbol)

            # 打印统计信息
            print(f"已有{len(already_listed_tokens)}个项目上线币安现货")
          
        await send_alpha_image(
            crypto_list=crypto_list,
            date=alpha_data.get('date', ''),
            debug_only=debug_only,
            max_items=100
        )

        return alpha_data
        
    except Exception as e:
        logger.exception(f"获取币安Alpha项目列表数据时出错: {str(e)}")
        print(f"错误: {str(e)}")
        return False

async def classify_crypto_projects_by_platform(crypto_list, platforms, platforms_to_process):
    """将加密货币项目按区块链平台分类
    
    Args:
        crypto_list: 加密货币项目列表
        platforms: 平台关键词字典
        platforms_to_process: 要处理的平台列表
        
    Returns:
        Tuple[Dict[str, List], List]: 按平台分类的项目字典和未分类的项目列表
    """
    # 初始化平台项目字典
    platform_projects = {platform: [] for platform in platforms_to_process}
    
    # 初始化未分类项目列表
    unclassified_projects = []
    
    # 创建平台名称到标准名称的映射
    platform_mapping = {}
    for std_name, keywords in platforms.items():
        for keyword in keywords:
            platform_mapping[keyword.lower()] = std_name
    
    # 添加完整平台名称作为直接映射
    for platform in platforms.keys():
        platform_mapping[platform.lower()] = platform
    
    # 处理每个加密货币项目
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
    
    # 如果有"Other"平台并且我们要处理它，将未分类的项目添加到Other类别
    if "Other" in platforms_to_process:
        platform_projects["Other"].extend(unclassified_projects)
        unclassified_projects = []
    
    # 输出分类统计
    print("\n按区块链平台分类结果:")
    for platform, projects in platform_projects.items():
        print(f"{platform}: {len(projects)}个项目")
    
    if unclassified_projects:
        print(f"未分类: {len(unclassified_projects)}个项目")
    
    # 使用crypto_formatter模块保存分类结果
    saved_paths = save_crypto_list_by_platform(platform_projects)
    print(f"\n已保存分类结果到data/platforms目录")
    
    return platform_projects, unclassified_projects

def determine_platforms_to_process(platforms):
    """
    确定要处理的平台列表
    
    Args:
        platforms: 可用的区块链平台字典
        
    Returns:
        list: 要处理的平台列表
    """
    # 使用配置文件中的PLATFORMS_TO_QUERY
    if PLATFORMS_TO_QUERY:
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

async def process_platform_advice(advisor, platform_data, max_retries, retry_delay, debug_only, platform):
    """处理单个平台的投资建议
    
    Args:
        advisor: AI顾问实例
        platform_data: 平台数据
        max_retries: 最大重试次数
        retry_delay: 重试延迟
        debug_only: 是否仅调试
        platform: 平台名称
        
    Returns:
        Tuple[str, str, bool]: 平台名称、投资建议、是否成功
    """
    print(f"正在为平台 {platform} ({len(platform_data['data']['cryptoCurrencyList'])}个项目) 获取投资建议...")
    
    # 获取投资建议
    advice = await advisor.get_investment_advice_async(
        platform_data, 
        max_retries=max_retries, 
        retry_delay=retry_delay,
        debug=True,
        dry_run=debug_only
    )
    
    if advice:
        # 发送建议
        if not debug_only:
            await send_message_async(advice)
        
        # 保存建议到文件
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        platform_filename = platform.lower().replace(' ', '_')
        advice_file = os.path.join(DATA_DIRS['advices'], f"advice_{timestamp}_{platform_filename}.md")
        
        with open(advice_file, 'w', encoding='utf-8') as f:
            f.write(advice)
            
        print(f"已保存{platform}平台投资建议到: {advice_file}")
        return platform, advice, True
    else:
        print(f"获取{platform}平台投资建议失败")
        return platform, "", False

async def prepare_platform_data(alpha_data=None, listed_tokens=None):
    """准备和处理平台数据（数据处理层）
    
    Args:
        alpha_data: 币安Alpha数据，如果为None则返回False
        listed_tokens: 已上线币安的token列表
        
    Returns:
        Dict 包含处理后的平台数据，失败时返回None
        {
            'date': str,
            'platform_data_list': List[Tuple[str, Dict]],
            'filtered_crypto_list': List[Dict],
            'platforms_to_process': List[str]
        }
    """
    print("=== 准备平台数据 ===\n")
    
    # 确认有Alpha数据
    if not alpha_data:
        logger.error("未提供币安Alpha数据，无法准备平台数据")
        print("错误: 未提供币安Alpha数据")
        return None
    
    # 提取项目列表
    crypto_list = alpha_data.get("data", {}).get("cryptoCurrencyList", [])
    date = alpha_data.get("date", "")
    
    if not crypto_list:
        logger.error("币安Alpha数据中未包含项目列表")
        print("错误: 币安Alpha数据中未包含项目列表")
        return None
    
    # 初始化filtered_crypto_list，默认使用原始crypto_list
    filtered_crypto_list = crypto_list
    
    # 如果提供了已上线Token列表，过滤掉这些token
    if listed_tokens and listed_tokens.get('all_tokens'):
        original_count = len(crypto_list)
        
        # 过滤标准形式和1000Token形式的token
        filtered_crypto_list = []
        
        for crypto in crypto_list:
            symbol = crypto.get("symbol", "")
            if not symbol:
                filtered_crypto_list.append(crypto)  # 保留没有symbol的项目
                continue
            
            if not is_token_listed(symbol):
                filtered_crypto_list.append(crypto)
        
        # 统计结果
        removed_count = original_count - len(filtered_crypto_list)
        
        # 打印详细过滤信息
        print(f"已从Alpha项目列表中移除{removed_count}个已上线的Token，剩余{len(filtered_crypto_list)}个项目")
        
        # 保存过滤后的数据
        save_crypto_data(filtered_crypto_list, f"filtered_crypto_list_{datetime.now().strftime('%Y%m%d%H%M%S')}.json", "filtered")
    else:
        print(f"未提供已上线Token列表或列表为空，将处理所有{len(filtered_crypto_list)}个Alpha项目")
    
    # 使用配置中的区块链平台定义
    platforms = BLOCKCHAIN_PLATFORMS
    
    # 确定要处理的平台列表
    platforms_to_process = determine_platforms_to_process(platforms)
    print(f"将处理以下平台: {', '.join(platforms_to_process)}\n")
    
    # 对项目按区块链平台分类
    platform_projects, unclassified_projects = await classify_crypto_projects_by_platform(
        filtered_crypto_list, platforms, platforms_to_process
    )
    
    # 准备平台数据
    platform_data_list = []
    for platform in platforms_to_process:
        projects = platform_projects.get(platform, [])
        if not projects:
            print(f"平台 {platform} 没有项目，跳过")
            continue
            
        # 准备针对当前平台的数据
        platform_data = {
            "data": {
                "cryptoCurrencyList": projects
            },
            "date": date,
            "platform": platform,
            "total_count": len(projects)
        }
        platform_data_list.append((platform, platform_data))
    
    return {
        'date': date,
        'platform_data_list': platform_data_list,
        'filtered_crypto_list': filtered_crypto_list,
        'platforms_to_process': platforms_to_process
    }


async def generate_investment_advice(prepared_data, debug_only=False):
    """生成AI投资建议（AI调用层）
    
    Args:
        prepared_data: 由prepare_platform_data返回的准备好的数据
        debug_only: 是否仅调试模式（只生成提示词不发送API请求）
        
    Returns:
        bool: 操作是否成功
    """
    print("=== 生成AI投资建议 ===\n")
    
    if not prepared_data:
        logger.error("未提供准备好的平台数据")
        print("错误: 未提供准备好的平台数据")
        return False
    
    # 提取准备好的数据
    date = prepared_data['date']
    platform_data_list = prepared_data['platform_data_list']
    platforms_to_process = prepared_data['platforms_to_process']
    
    if not platform_data_list:
        print("没有需要处理的平台数据")
        return False
    
    # 初始化AI顾问
    advisor = AlphaAdvisor()
    
    # 设置重试参数
    max_retries = 1
    retry_delay = 2.0
    
    # 创建建议目录
    advice_dir = DATA_DIRS['advices']
    os.makedirs(advice_dir, exist_ok=True)
    os.makedirs(DATA_DIRS['all-platforms'], exist_ok=True)
    
    # 按平台获取投资建议
    results = {}
    failed_platforms = []
    all_advice = f"# 币安Alpha项目投资建议 (按区块链平台分类，{date})\n\n"
    
    # 并行处理所有平台
    tasks = []
    for platform, platform_data in platform_data_list:
        task = process_platform_advice(
            advisor, 
            platform_data, 
            max_retries, 
            retry_delay, 
            debug_only, 
            platform
        )
        tasks.append(task)
    
    # 等待所有任务完成
    platform_results = await asyncio.gather(*tasks)
    
    # 处理结果
    for platform, advice, success in platform_results:
        if success:
            results[platform] = advice
            all_advice += f"## {platform}平台投资建议\n\n{advice}\n\n---\n\n"
        else:
            failed_platforms.append(platform)
    
    # 保存所有平台的建议到一个文件
    if results:
        timestamp = datetime.now().strftime('%Y%m%d')
        all_advice_file = os.path.join(DATA_DIRS['all-platforms'], f"advice_{timestamp}_all_platforms.md")
        
        with open(all_advice_file, 'w', encoding='utf-8') as f:
            f.write(all_advice)
            
        print(f"\n已保存所有平台的投资建议到: {all_advice_file}")
    
    # 打印总结
    print("\n投资建议获取总结:")
    print(f"成功: {len(results)}/{len(platforms_to_process)} 个平台")
    
    if failed_platforms:
        print(f"失败: {', '.join(failed_platforms)}")
        
    return len(results) > 0


async def get_alpha_investment_advice(prepared_data=None, debug_only=False):
    """获取基于当天币安Alpha数据的AI投资建议，按不同区块链平台分类
    
    Args:
        prepared_data: 准备好的数据，如果为None则重新获取
        debug_only: 是否仅调试模式（只生成提示词不发送API请求）
        
    Returns:
        bool: 操作是否成功
    """
    print("=== 币安Alpha投资建议 ===\n")
    
    return await generate_investment_advice(prepared_data, debug_only)


async def run_workflow(debug_only=False, AI_needed=True, volume_monitor=True):
    """运行完整工作流：图片生成 + AI投资分析
    
    Args:
        debug_only: 是否仅调试模式（不发送消息）
        AI_needed: 是否需要AI投资分析
        volume_monitor: 是否启用交易量监控（默认开启）
    """
    try:
        # 步骤1: 获取并更新Binance交易对列表
        print("步骤1: 获取并更新Binance交易对列表...\n")
        listed_tokens = await get_binance_tokens()
        
        # 步骤2: 获取币安Alpha项目列表数据并推送图片
        print("步骤2.1: 获取币安Alpha项目列表数据并推送图片...\n")
        alpha_data = await get_binance_alpha_list(
            listed_tokens=listed_tokens, 
            debug_only=debug_only, 
        )
        
        if not alpha_data:
            logger.error("获取币安Alpha项目列表数据失败，程序退出")
            print("\n错误: 获取币安Alpha项目列表数据失败，程序退出")
            return 1
        
        # 数据处理
        print("\n步骤2.2: 数据处理...\n")
        prepared_data = await prepare_platform_data(alpha_data, listed_tokens)


        # 步骤3: 分类项目并生成投资建议
        print("\n步骤3: 分类项目并生成投资建议...\n")
        
        if not AI_needed:
            print("AI投资分析已禁用，程序退出")
            return 0
        
        # 按区块链平台获取AI投资建议
        await get_alpha_investment_advice(
            prepared_data, 
            debug_only=debug_only,
        )
        
    except Exception as e:
        logger.error(f"工作流执行过程中出错: {str(e)}")
        print(f"\n错误: {str(e)}")
        import traceback
        error_details = traceback.format_exc()
        logger.debug(error_details)
        print("错误详情已记录到日志文件")
        return 1

async def main():
    """主函数
    
    运行完整工作流：获取数据、生成图片、AI投资分析
    """
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Crypto Monitor - 币安Alpha项目分析工具")
    parser.add_argument("--debug-only", action="store_true", 
                       help="启用调试模式，仅获取数据推送图片，不进行AI分析")
    parser.add_argument("--AI-needed", action="store_true", 
                       help="启用AI投资分析")
    parser.add_argument("--no-volume-monitor", action="store_true",
                       help="禁用交易量监控（默认开启）")
    args = parser.parse_args()
    
    workflow_start_time = time.time()

    # 运行完整工作流
    await run_workflow(
        debug_only=args.debug_only, 
        AI_needed=args.AI_needed,
        volume_monitor=not args.no_volume_monitor
    )

    total_time = time.time() - workflow_start_time
    print(f"\n⏱️  总运行时长: {total_time:.2f}秒 ({total_time/60:.2f}分钟)")

if __name__ == "__main__":
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main()) 