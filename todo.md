1. 命令行参数调整
```
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Crypto Monitor - 币安Alpha项目分析工具")
    parser.add_argument("--coinmarket-only", action="store_true", 
                       help="仅获取CoinMarket数据并推送图片，不进行AI分析")
    parser.add_argument("--debug-only", action="store_true", 
                       help="启用调试模式，仅生成提示词不发送API请求")
    parser.add_argument("--platform", type=str, choices=supported_platforms, 
                       help=f"指定要处理的平台（仅在调试模式下有效）: {', '.join(supported_platforms)}")
    parser.add_argument("--force-update", action="store_true", 
                       help="强制更新数据，不使用缓存")
    parser.add_argument("--skip-tokens-update", action="store_true", 
                       help="跳过更新Binance交易对列表")
    args = parser.parse_args()
```
移除platform/force-update/skip-tokens-update
移除相关的代码处理逻辑

2. 移除使用CoinmarketOnly的单独生成图片推送的分支处理， 现在默认就是要生成图片和AI分析功能两个逻辑一起执行

3. docs-viewer中把生成的图片资源也添加到预览模块中， 使用tab来区分文档和图片