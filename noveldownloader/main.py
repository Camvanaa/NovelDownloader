import argparse
import json
import os
import importlib
import logging # 导入 logging 模块
from noveldownloader.utils.logger import setup_logger # 确保路径正确
from typing import List, Optional # 用于类型提示

# 默认配置和输出目录
DEFAULT_CONFIG_DIR = "configs"
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_CACHE_DIR = "cache"
DEFAULT_LOG_FILE = "logs/app.log" # <--- 取消注释

# 在模块级别声明 logger，稍后由 main 函数中的 setup_logger 初始化
# 这个 logger 将是 "NovelDownloaderApp"
logger = logging.getLogger("NovelDownloaderApp")

def parse_chapter_selection(selection_str: Optional[str]) -> Optional[List[int]]:
    """
    解析章节选择字符串 (例如 "1-5,8,10-12") 为一个整数列表。
    返回的章节号是1-based。
    """
    if not selection_str:
        return None
    
    selected_chapters = set()
    parts = selection_str.split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                start, end = map(int, part.split('-', 1))
                if start <= 0 or end <= 0 or start > end:
                    logger.warning(f"无效的章节范围: {part}。章节号必须为正数且起始不大于结束。已忽略。")
                    continue
                selected_chapters.update(range(start, end + 1))
            except ValueError:
                logger.warning(f"无效的章节范围格式: {part}。应为 '数字-数字'。已忽略。")
                continue
        else:
            try:
                chapter_num = int(part)
                if chapter_num <= 0:
                    logger.warning(f"无效的章节号: {part}。章节号必须为正数。已忽略。")
                    continue
                selected_chapters.add(chapter_num)
            except ValueError:
                logger.warning(f"无效的章节号格式: {part}。应为单个数字。已忽略。")
                continue
    
    if not selected_chapters:
        logger.warning("章节选择参数被指定，但未解析出任何有效章节。将下载所有章节。")
        return None
        
    return sorted(list(selected_chapters))

def load_config(config_path: str) -> dict:
    """加载 JSON 配置文件。"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        logger.error(f"配置文件未找到: {config_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"配置文件解析失败: {config_path}, 错误: {e}")
        raise
    except Exception as e:
        logger.error(f"加载配置文件时发生未知错误: {config_path}, 错误: {e}")
        raise

def get_downloader_instance(config: dict, cache_root_dir: str):
    """根据配置动态加载并实例化下载器。"""
    downloader_class_name = config.get("downloader_class")
    # parser_class_name = config.get("parser_class") # 解析器由下载器自行处理
    site_name = config.get("site_name", "default_site")

    if not downloader_class_name:
        logger.error("配置中缺少 'downloader_class' 定义。")
        return None

    try:
        # 构建下载器模块的导入路径，例如 noveldownloader.downloaders.example_downloader
        # 我们假设下载器类名 ExampleDownloader 对应的模块是 example_downloader.py
        module_short_name = downloader_class_name.lower().replace("downloader", "")
        if not module_short_name:
             module_short_name = "base" # 以防万一类名就是 Downloader
        
        # 完整的模块路径应该是 noveldownloader.downloaders.[module_short_name]_downloader
        # 但 import_module 通常相对于当前包或顶级包工作，取决于如何运行
        # 为了从项目根目录运行 main.py 时能正确找到，使用绝对导入路径
        downloader_module_path = f"noveldownloader.downloaders.{module_short_name}_downloader"
        
        logger.debug(f"尝试导入下载器模块: {downloader_module_path}")
        downloader_module = importlib.import_module(downloader_module_path)
        
        DownloaderClass = getattr(downloader_module, downloader_class_name)
        
        site_cache_dir = os.path.join(cache_root_dir, site_name)
        
        downloader_instance = DownloaderClass(site_config=config, cache_dir=site_cache_dir)
        logger.info(f"成功实例化下载器: {downloader_class_name} for site: {site_name}")
        return downloader_instance
        
    except ImportError as e:
        logger.error(f"导入模块失败: {e}. 尝试的路径: {downloader_module_path}")
        return None
    except AttributeError as e:
        logger.error(f"在模块 {downloader_module_path} 中找不到类 {downloader_class_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"实例化下载器时发生错误: {e}", exc_info=True)
        return None

def main():
    parser = argparse.ArgumentParser(description="小说下载器")
    parser.add_argument(
        "config_file", 
        type=str, 
        help=f"网站配置文件名 (例如: example_site_config.json)。将在 '{DEFAULT_CONFIG_DIR}' 目录下查找。"
    )
    parser.add_argument(
        "-o", "--output_dir", 
        type=str, 
        default=DEFAULT_OUTPUT_DIR, 
        help=f"小说下载到的目录 (默认: {DEFAULT_OUTPUT_DIR}) 。"
    )
    parser.add_argument(
        "-c", "--cache_dir", 
        type=str, 
        default=DEFAULT_CACHE_DIR, 
        help=f"缓存文件存放的根目录 (默认: {DEFAULT_CACHE_DIR}) 。"
    )
    parser.add_argument(
        "--log_file", 
        type=str, 
        default=None, 
        help=f"日志文件路径。如果未指定，则使用 configs/[config_name].log 或 {DEFAULT_LOG_FILE}。"
    )
    parser.add_argument(
        "--log_level", 
        type=str, 
        default="INFO", 
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
        help="日志级别 (默认: INFO)"
    )
    parser.add_argument(
        "--clear_cache", 
        action="store_true", 
        help="在开始下载前清空该网站的缓存。"
    )
    parser.add_argument(
        "--url", 
        type=str, 
        default=None, 
        help="要下载的小说URL。如果未提供，则使用配置文件中的 start_url。"
    )
    parser.add_argument(
        "--chapters",
        type=str,
        default=None,
        help="指定下载的章节范围或列表。例如: '1-5,8,10-12'。如果未提供，则下载所有章节。"
    )
    parser.add_argument(
        "--list-chapters",
        action="store_true",
        help="仅获取并打印小说目录，不下载章节内容。"
    )

    args = parser.parse_args()

    # -- 配置日志 --
    # 1. 获取命令行指定的日志级别
    cli_log_level_str = args.log_level.upper()
    cli_log_level_val = getattr(logging, cli_log_level_str, logging.INFO)

    # 2. 配置根记录器 (root logger)
    #    - 设置其级别，以便捕获所有模块中达到此级别的日志。
    #    - 如果根记录器还没有任何处理程序，则添加一个基本的控制台处理程序。
    #      这样可以确保来自任何模块（如 parsers）且传播到根的日志都能被显示。
    root_logger = logging.getLogger()
    root_logger.setLevel(cli_log_level_val) 

    if not root_logger.hasHandlers() and cli_log_level_val <= logging.DEBUG: # 只在需要详细日志且无handler时添加
        console_handler = logging.StreamHandler()
        # 可以设置一个简单的格式，或者让 setup_logger 中的格式更优先（如果适用）
        # formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # console_handler.setFormatter(formatter)
        console_handler.setLevel(cli_log_level_val) # 确保控制台handler也接受这个级别
        root_logger.addHandler(console_handler)
        # logger.debug("已为根记录器添加控制台处理程序。") # 用根logger或NovelDownloaderApp logger记录

    # 3. 配置主应用程序记录器 ("NovelDownloaderApp")
    # global logger # logger 已经在模块级别获取
    log_file_name = os.path.splitext(args.config_file)[0] + ".log" if args.config_file else "app.log"
    effective_log_file = args.log_file if args.log_file else os.path.join("logs", log_file_name)
    
    log_dir = os.path.dirname(effective_log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
        # print(f"创建日志目录: {log_dir}") # 在logger配置前打印

    # setup_logger 应该会为 "NovelDownloaderApp" 设置级别、格式化器和文件/控制台处理程序
    # logger 已被赋值为 logging.getLogger("NovelDownloaderApp")
    setup_logger( 
        logger_instance=logger, # 传递已获取的 logger 实例
        log_level=cli_log_level_val,
        log_file=effective_log_file,
        log_to_console=True # <--- 修正参数名
    )
    
    logger.info(f"应用启动，参数: {args}")
    if cli_log_level_val == logging.DEBUG:
        logger.debug("调试模式已激活。根记录器级别: %s, NovelDownloaderApp 级别: %s", 
                     logging.getLevelName(root_logger.getEffectiveLevel()), 
                     logging.getLevelName(logger.getEffectiveLevel()))


    config_path = os.path.join(DEFAULT_CONFIG_DIR, args.config_file)

    try:
        site_config = load_config(config_path)
        logger.info(f"成功加载配置文件: {config_path}")
    except Exception:
        logger.critical("无法启动，请检查配置文件路径或内容。程序退出。")
        return

    downloader = get_downloader_instance(site_config, args.cache_dir)

    if not downloader:
        logger.critical("无法初始化下载器，程序退出。")
        return

    if args.clear_cache:
        if hasattr(downloader, 'cache') and hasattr(downloader.cache, 'clear'):
            logger.info(f"正在清空网站 {site_config.get('site_name', 'unknown_site')} 的缓存...")
            downloader.cache.clear()
            logger.info("缓存已清空。")
        else:
            logger.warning("下载器没有正确配置缓存或不支持清空缓存操作。")

    novel_url_to_download = args.url if args.url else site_config.get("start_url")

    if not novel_url_to_download:
        logger.error("错误: 必须通过 --url 参数或在配置文件中指定 'start_url' 来提供小说URL。")
        return

    selected_chapters_list = parse_chapter_selection(args.chapters)
    if selected_chapters_list:
        logger.info(f"用户指定下载章节: {selected_chapters_list}")

    if not os.path.exists(args.output_dir):
        try:
            os.makedirs(args.output_dir)
            logger.info(f"创建输出目录: {args.output_dir}")
        except OSError as e:
            logger.error(f"创建输出目录失败: {args.output_dir}, 错误: {e}")
            return

    try:
        if args.list_chapters:
            logger.info(f"仅列出章节模式，URL: {novel_url_to_download}")
            downloader.list_chapters(novel_url_to_download)
        else:
            logger.info(f"开始下载小说，URL: {novel_url_to_download}")
            downloader.download_novel(novel_url_to_download, args.output_dir, selected_chapters=selected_chapters_list)
            logger.info("小说下载任务完成。")
    except Exception as e:
        logger.error(f"下载小说时发生严重错误: {e}", exc_info=True)
        logger.info("小说下载任务因错误而中止。")

if __name__ == "__main__":
    main() 