"""
数据清理模块
按照 config.DATA_RETENTION 策略自动清理过期的历史数据文件
"""

import os
import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from config import DATA_DIRS, DATA_RETENTION

logger = logging.getLogger(__name__)

# 文件名中日期的正则模式：匹配 YYYYMMDD 或 YYYYMMDDHHmmSS
_DATE_PATTERN = re.compile(r'(\d{8})')


def _extract_file_date(filename: str) -> datetime | None:
    """从文件名中提取日期，返回 datetime 或 None"""
    match = _DATE_PATTERN.search(filename)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), '%Y%m%d')
    except ValueError:
        return None


def _cleanup_directory(
    directory: str,
    pattern: str,
    retention_days: int,
    cutoff_date: datetime,
) -> Tuple[int, int]:
    """
    清理目录中匹配 pattern 的过期文件

    Returns:
        (deleted_count, freed_bytes)
    """
    if not os.path.isdir(directory):
        return 0, 0

    deleted_count = 0
    freed_bytes = 0

    for filename in os.listdir(directory):
        if not re.match(pattern, filename):
            continue

        file_date = _extract_file_date(filename)
        if file_date is None:
            continue

        if file_date >= cutoff_date:
            continue

        filepath = os.path.join(directory, filename)
        if not os.path.isfile(filepath):
            continue

        try:
            file_size = os.path.getsize(filepath)
            os.remove(filepath)
            deleted_count += 1
            freed_bytes += file_size
        except OSError as e:
            logger.warning(f"删除失败 {filepath}: {e}")

    return deleted_count, freed_bytes


def cleanup_old_data(dry_run: bool = False) -> Dict[str, Tuple[int, int]]:
    """
    根据 DATA_RETENTION 配置清理过期数据文件

    Args:
        dry_run: 如果 True，只打印将要删除的文件，不实际删除

    Returns:
        Dict[category, (deleted_count, freed_bytes)]
    """
    now = datetime.now()
    results: Dict[str, Tuple[int, int]] = {}

    cleanup_tasks = [
        (
            'images',
            DATA_DIRS.get('images', 'images'),
            r'(alpha_list|top_vol_mc_ratio|gainers_losers)_\d{14}\.png$',
            DATA_RETENTION.get('images', 30),
        ),
        (
            'filtered_crypto_list',
            DATA_DIRS.get('data', 'data'),
            r'filtered_crypto_list_\d+\.json$',
            DATA_RETENTION.get('filtered_crypto_list', 30),
        ),
        (
            'alpha_crypto_list',
            DATA_DIRS.get('data', 'data'),
            r'alpha_crypto_list_.*_\d+\.json$',
            DATA_RETENTION.get('alpha_crypto_list', 30),
        ),
        (
            'trend_signals',
            DATA_DIRS.get('data', 'data'),
            r'trend_signals_\d+\.json$',
            DATA_RETENTION.get('trend_signals', 60),
        ),
        (
            'platforms',
            os.path.join(DATA_DIRS.get('data', 'data'), 'platforms'),
            r'.+_projects_\d+\.json$',
            DATA_RETENTION.get('platforms', 30),
        ),
        # advices 由 git 追踪，不自动清理
        (
            'prompts',
            DATA_DIRS.get('prompts', 'prompts'),
            r'.+\.(txt|md|json)$',
            DATA_RETENTION.get('prompts', 30),
        ),
    ]

    total_deleted = 0
    total_freed = 0

    for category, directory, pattern, retention_days in cleanup_tasks:
        cutoff_date = now - timedelta(days=retention_days)

        if dry_run:
            count, size = _count_expired_files(directory, pattern, cutoff_date)
            action = "将删除"
        else:
            count, size = _cleanup_directory(directory, pattern, retention_days, cutoff_date)
            action = "已删除"

        results[category] = (count, size)
        total_deleted += count
        total_freed += size

        if count > 0:
            logger.info(
                f"[{category}] {action} {count} 个文件, "
                f"释放 {size / 1024 / 1024:.1f}MB "
                f"(保留 {retention_days} 天, 截止 {cutoff_date.strftime('%Y-%m-%d')})"
            )

    # 清理 docs-viewer/public 下的副本
    public_cleanup_dirs = [
        ('docs-viewer/public/images', r'(alpha_list|top_vol_mc_ratio|gainers_losers)_\d{14}\.png$', DATA_RETENTION.get('images', 30)),
        ('docs-viewer/public/tables', r'(filtered_crypto_list|trend_signals)_\d+\.json$', DATA_RETENTION.get('filtered_crypto_list', 30)),
    ]

    for directory, pattern, retention_days in public_cleanup_dirs:
        cutoff_date = now - timedelta(days=retention_days)
        if dry_run:
            count, size = _count_expired_files(directory, pattern, cutoff_date)
        else:
            count, size = _cleanup_directory(directory, pattern, retention_days, cutoff_date)

        total_deleted += count
        total_freed += size
        results[f"public/{os.path.basename(directory)}"] = (count, size)

    mode_label = "Dry-run" if dry_run else "清理完成"
    logger.info(
        f"[{mode_label}] 共 {total_deleted} 个文件, "
        f"释放 {total_freed / 1024 / 1024:.1f}MB"
    )

    return results


def _count_expired_files(
    directory: str,
    pattern: str,
    cutoff_date: datetime,
) -> Tuple[int, int]:
    """统计将要被清理的文件（dry-run 用）"""
    if not os.path.isdir(directory):
        return 0, 0

    count = 0
    total_size = 0

    for filename in os.listdir(directory):
        if not re.match(pattern, filename):
            continue

        file_date = _extract_file_date(filename)
        if file_date is None or file_date >= cutoff_date:
            continue

        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            count += 1
            total_size += os.path.getsize(filepath)

    return count, total_size


if __name__ == '__main__':
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )

    parser = argparse.ArgumentParser(description='清理过期的历史数据文件')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅预览将要删除的文件，不实际删除',
    )
    args = parser.parse_args()

    results = cleanup_old_data(dry_run=args.dry_run)

    print("\n=== 清理报告 ===")
    total_count = 0
    total_size = 0
    for category, (count, size) in results.items():
        if count > 0:
            print(f"  {category}: {count} 个文件, {size / 1024 / 1024:.1f}MB")
            total_count += count
            total_size += size

    print(f"\n  总计: {total_count} 个文件, {total_size / 1024 / 1024:.1f}MB")

    if args.dry_run:
        print("\n  (Dry-run 模式，未实际删除)")
