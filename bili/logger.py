# -*- coding: utf-8 -*-
"""带颜色的控制台日志。Windows 下自动启用 ANSI。"""
import os
import sys
import threading
from datetime import datetime

try:
    import colorama

    colorama.just_fix_windows_console()
    _HAVE_COLORAMA = True
except Exception:  # pragma: no cover
    _HAVE_COLORAMA = False

_RESET = "\033[0m"
_GRAY = "\033[90m"
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_BLUE = "\033[94m"
_MAGENTA = "\033[95m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"

_lock = threading.Lock()


def _color_enabled():
    if os.environ.get("NO_COLOR"):
        return False
    if _HAVE_COLORAMA:
        return True
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


_COLOR = _color_enabled()


def _c(text, code):
    return f"{code}{text}{_RESET}" if _COLOR else text


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def info(msg, prefix=None):
    with _lock:
        head = f"[{_ts()}]" if _COLOR else f"[{_ts()}]"
        if prefix:
            head += f" {_c(prefix, _CYAN)}"
        print(f"{head} {msg}", flush=True)


def ok(msg, prefix=None):
    info(_c(msg, _GREEN), prefix)


def warn(msg, prefix=None):
    info(_c(msg, _YELLOW), prefix)


def error(msg, prefix=None):
    info(_c(msg, _RED), prefix)


def debug(msg, prefix=None):
    if os.environ.get("BILI_DEBUG"):
        info(_c(msg, _GRAY), prefix)


def section(title):
    """打印任务分区标题。"""
    with _lock:
        print(flush=True)
        print(_c(f"{'=' * 10} {title} {'=' * 10}", _BOLD), flush=True)


def summary_table(rows):
    """rows: list of (account, ok_count, fail_count, details_str)"""
    with _lock:
        print(flush=True)
        print(_c("=" * 62, _BOLD), flush=True)
        print(_c("运行结果汇总", _BOLD), flush=True)
        print(_c("-" * 62, _BOLD), flush=True)
        for uid, okc, failc, detail in rows:
            status = _c("OK", _GREEN) if failc == 0 else _c("异常", _RED)
            print(
                f"  {_c(uid, _CYAN)}: {status}  成功 {okc} / 失败 {failc}",
                flush=True,
            )
            if detail:
                for line in detail:
                    print(f"      {line}", flush=True)
        print(_c("=" * 62, _BOLD), flush=True)
