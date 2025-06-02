import logging
import sys
import os

LOG_LEVEL = logging.INFO #默认日志级别
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

def setup_logger(name="noveldownloader", log_level=None, log_file=None, log_to_console=True, logger_instance=None):
    """
    设置和配置一个日志记录器。

    Args:
        name (str): 日志记录器的名称 (如果 logger_instance 未提供).
        log_level (int, optional): 日志级别 (例如 logging.INFO, logging.DEBUG).
                                   默认为模块级的 LOG_LEVEL.
        log_file (str, optional): 日志输出到的文件路径。如果为 None，则不输出到文件。
        log_to_console (bool): 是否将日志输出到控制台。
        logger_instance (logging.Logger, optional): 一个已存在的 logger 实例。
                                                    如果提供，则配置此实例，忽略 name 参数。

    Returns:
        logging.Logger: 配置好的日志记录器实例。
    """
    level = log_level if log_level is not None else LOG_LEVEL
    
    # 使用提供的 logger_instance (如果可用)，否则根据 name 获取/创建 logger
    effective_logger = logger_instance if logger_instance else logging.getLogger(name)
    effective_logger.setLevel(level) # 为此 logger 设置级别

    # 防止重复添加 handlers，或者如果配置改变则清空旧 handlers
    if effective_logger.hasHandlers():
        effective_logger.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT)

    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level) # <--- 确保处理器级别被设置
        effective_logger.addHandler(console_handler)

    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            file_handler.setLevel(level) # <--- 确保处理器级别被设置
            effective_logger.addHandler(file_handler)
        except Exception as e:
            print(f"错误：无法设置文件日志记录器到 {log_file}: {e}", file=sys.stderr)
            # 即使文件日志失败，也尝试用 effective_logger 记录错误（如果它有控制台handler）
            effective_logger.error(f"无法设置文件日志记录器到 {log_file}: {e}")

    return effective_logger

# 创建一个默认的logger实例，可以在其他模块中直接导入使用
# 例如: from .logger import logger
# logger.info("这是一条日志信息")

# logger = setup_logger() # 在这里初始化可能会导致循环导入或配置问题，
                        # 推荐在使用时按需创建或在主程序入口处创建。

if __name__ == '__main__':
    # 模块内测试
    # 测试控制台输出
    test_logger_console = setup_logger("TestConsoleLogger", log_level=logging.DEBUG)
    test_logger_console.debug("这是一条 DEBUG 信息 (控制台)")
    test_logger_console.info("这是一条 INFO 信息 (控制台)")
    test_logger_console.warning("这是一条 WARNING 信息 (控制台)")
    test_logger_console.error("这是一条 ERROR 信息 (控制台)")
    test_logger_console.critical("这是一条 CRITICAL 信息 (控制台)")

    print("-" * 30)

    # 测试文件输出 (假设在项目根目录下运行，会创建 logs/app.log)
    log_file_path = "logs/app_test.log"
    # 先尝试删除旧的测试日志文件
    if os.path.exists(log_file_path):
        try:
            os.remove(log_file_path)
        except OSError:
            pass # 忽略删除失败
            
    test_logger_file = setup_logger("TestFileLogger", log_level=logging.INFO, log_file=log_file_path)
    test_logger_file.debug("这是一条 DEBUG 信息 (文件) - 不应出现在文件中")
    test_logger_file.info("这是一条 INFO 信息 (文件)")
    test_logger_file.warning("这是一条 WARNING 信息 (文件)")
    
    # 测试同时输出到控制台和文件
    test_logger_both = setup_logger("TestBothLogger", log_level=logging.DEBUG, log_file=log_file_path, log_to_console=True)
    # 由于 TestFileLogger 已经添加了 handler 到同一个文件，这里 TestBothLogger 也会写入。
    # 更好的做法是，如果 log_file 相同，getLogger(name) 应该返回同一个 logger 实例，
    # setup_logger 内部的 clear() 会处理 handlers。
    # 但如果 name 不同，它们是不同的 logger 实例，会独立写入。
    # 为了避免重复日志，通常一个 name 对应一个 logger 实例。
    test_logger_both.info("--- TestBothLogger 开始 ---")
    test_logger_both.debug("这是一条 DEBUG 信息 (Both)")
    test_logger_both.info("这是一条 INFO 信息 (Both)")

    print(f"\n文件日志已写入到: {os.path.abspath(log_file_path)}")
    print("请检查该文件内容。")
    print("\nLogger 模块测试完成。") 