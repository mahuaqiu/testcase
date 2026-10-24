"""报告日志收集器单元测试。"""


def test_set_current_binds_logger_to_current_thread():
    """set_current 将指定 logger 绑定到当前线程（并行线程注入主线程实例）。"""
    import threading

    from common.report_logger import ReportLogger

    main_logger = ReportLogger.get_current()
    seen = {}

    def worker():
        seen["logger"] = ReportLogger.get_current()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    # 子线程默认拿到自己的新实例
    assert seen["logger"] is not main_logger

    def injected_worker():
        ReportLogger.set_current(main_logger)
        seen["injected"] = ReportLogger.get_current()

    thread = threading.Thread(target=injected_worker)
    thread.start()
    thread.join()
    # set_current 注入后子线程拿到主线程实例
    assert seen["injected"] is main_logger
