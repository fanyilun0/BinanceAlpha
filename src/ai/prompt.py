"""
提示词生成模块 - 为DeepSeek API提供各种场景的提示词模板

此模块负责:
1. 定义和管理各种提示词模板
2. 根据输入参数生成格式化的提示词
3. 提供通用的提示词工具函数
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Union

# 导入配置
from config import DATA_DIRS

# 设置日志
logger = logging.getLogger(__name__)

def save_list_data_for_debug(data_list: List[Dict], filename_prefix: str = "list_data") -> str:
    """保存列表数据到文件用于调试
    
    Args:
        data_list: 要保存的数据列表
        filename_prefix: 文件名前缀
        
    Returns:
        保存的文件路径
    """
    try:
        # 确保调试目录存在
        data_dir = DATA_DIRS.get('data', 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        # 创建文件名
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"{filename_prefix}_{timestamp}.json"
        file_path = os.path.join(data_dir, filename)
        
        # 保存到文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, ensure_ascii=False, indent=2)
        
        logger.info(f"已保存列表数据到: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"保存列表数据时出错: {str(e)}")
        return ""

    """生成加密货币Token筛选的提示词模板
    
    Args:
        current_date: 当前日期
        data_json: Token列表数据JSON
        
    Returns:
        格式化后的提示词模板
    """
    return f"""你是我的专业加密货币投资分析师，精通技术分析、基本面分析和市场趋势判断。根据当前市场数据({current_date})，从提供的token列表中筛选出最具投资价值的项目。请使用Markdown格式回答，使输出更易于阅读。

投资需求:
- 投资预算: 小额投资 (1000美元)
- 风险偏好: 高风险（追求高回报，愿意承担较大波动）
- 投资周期: 短期到中期（1-6个月）

请从以下token列表中分析筛选：
{data_json}

请按照以下Markdown格式结构提供分析和建议：

## 一、市场概况分析
*[简要分析当前加密市场环境、热点领域、市场情绪状态]*

## 二、Token筛选结果
### 最佳投资标的（选出3-5个最有价值的token）

| 代币名称 | 代号 | 当前价格 | 流通市值 | FDV | 流通率 | 应用场景 |
|---------|-----|---------|---------|-----|-------|--------|
| [名称1] | [代号1] | $[价格] | $[流通市值] | $[FDV] | [流通率]% | [场景] |
| [名称2] | [代号2] | $[价格] | $[流通市值] | $[FDV] | [流通率]% | [场景] |
| [名称3] | [代号3] | $[价格] | $[流通市值] | $[FDV] | [流通率]% | [场景] |

#### 推荐理由
1. **[代币1]**:
   - [优势1]
   - [优势2]
   - [优势3]

2. **[代币2]**:
   - [优势1]
   - [优势2]
   - [优势3]

3. **[代币3]**:
   - [优势1]
   - [优势2]
   - [优势3]

## 三、投资策略建议
### 1. 资金分配
| 代币代号 | 分配比例 |
|---------|---------|
| [代号1] | [比例]% |
| [代号2] | [比例]% |
| [代号3] | [比例]% |

### 2. 入场策略
| 代币代号 | 理想买入区间 | 技术指标条件 |
|---------|------------|------------|
| [代号1] | $[低价]-$[高价] | [条件] |
| [代号2] | $[低价]-$[高价] | [条件] |
| [代号3] | $[低价]-$[高价] | [条件] |

### 3. 风险管理
| 代币代号 | 止损位 | 风险控制建议 |
|---------|--------|------------|
| [代号1] | $[价格] | [建议] |
| [代号2] | $[价格] | [建议] |
| [代号3] | $[价格] | [建议] |

### 4. 获利目标
| 代币代号 | 短期目标 | 中期目标 | 预期回报率 |
|---------|---------|---------|-----------|
| [代号1] | $[价格] | $[价格] | [比例]% |
| [代号2] | $[价格] | $[价格] | [比例]% |
| [代号3] | $[价格] | $[价格] | [比例]% |

## 四、风险提示
- **[风险1]**: [规避建议]
- **[风险2]**: [规避建议]
- **[风险3]**: [规避建议]
- **[风险4]**: [规避建议]
- **[风险5]**: [规避建议]

请提供全面分析和精确建议，所有建议必须基于已提供的数据，给出具体可执行的策略。
""" 