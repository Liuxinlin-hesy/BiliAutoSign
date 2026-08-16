# -*- coding: utf-8 -*-
"""配置加载：config.json（不存在时从 config.example.json 自动生成）+
青龙面板环境变量支持。

青龙环境变量（优先级高于 config.json 的 cookies）：
- BILI_COOKIE：一个或多个 cookie，多账号用换行分隔
- Ray_BiliBiliCookies__0 / __1 / ...：BiliBiliToolPro 兼容命名，按序号从 0 起
"""
import copy
import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "config.json")
EXAMPLE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "config.example.json")

DEFAULT_CONFIG = {
    "cookies": [],
    "tasks": ["daily", "live", "manga", "vip"],
    # 每日任务选项
    "is_watch_video": True,
    "is_share_video": True,
    "number_of_coins": 5,
    "number_of_protected_coins": 0,
    "select_like": False,
    "save_coins_when_lv6": False,
    "support_up_ids": [],
    # 直播
    "is_silver2coin": True,
    # 漫画
    "device_platform": "android",
    "custom_comic_id": 0,
    "custom_ep_id": 0,
    # 风控与网络
    "interval_seconds_between_request_api": 3,
    "random_sleep_max_min": 0,
    "enable_bili_ticket": True,
    "timeout": 20,
    "retries": 2,
    "user_agent": "",
    "web_proxy": "",
    # 可选任务（默认关闭）
    "enable_lottery": False,
    "enable_fans_medal": False,
    "fans_medal_like_number": 5,
    "fans_medal_heartbeat_number": 30,
    # 青龙面板通知（OpenAPI）
    "ql_base_url": "",
    "ql_client_id": "",
    "ql_client_secret": "",
    "notify_fail_only": True,
    # 其他
    "persist_cookies": True,
}


def get_env(name: str):
    """大小写不敏感的环境变量读取（兼容 Windows/PowerShell 将变量名大写化的情况）。"""
    val = os.environ.get(name)
    if val is not None:
        return val
    upper = name.upper()
    for k, v in os.environ.items():
        if k.upper() == upper:
            return v
    return None


def load_env_cookies() -> tuple:
    """从青龙环境变量读取 cookie。

    返回 (cookie字符串列表, 来源标志)；无环境变量时返回 ([], False)。
    """
    cookies = []
    # 1) BILI_COOKIE：多行分隔多账号
    env_ck = (get_env("BILI_COOKIE") or "").strip()
    if env_ck:
        for line in env_ck.replace("\r\n", "\n").split("\n"):
            line = line.strip()
            if line:
                cookies.append(line)
    # 2) Ray_BiliBiliCookies__N：BiliBiliToolPro 兼容，按序号排序
    named = {}
    for k, v in os.environ.items():
        if k.upper().startswith("RAY_BILIBILICOOKIES__") and v.strip():
            try:
                idx = int(k.split("__")[-1])
            except ValueError:
                continue
            named[idx] = v.strip()
    for _, v in sorted(named.items()):
        if v not in cookies:
            cookies.append(v)
    return cookies, bool(cookies)


def ql_env_config() -> dict:
    """青龙通知相关配置（环境变量优先，其次 config.json）。"""
    cfg = {
        "ql_base_url": (get_env("QL_BASE_URL") or "").strip(),
        "ql_client_id": (get_env("QL_CLIENT_ID") or "").strip(),
        "ql_client_secret": (get_env("QL_CLIENT_SECRET") or "").strip(),
        "notify_fail_only": (get_env("QL_NOTIFY_FAIL_ONLY") or "").strip(),
    }
    return cfg


# 环境变量 -> 配置项映射（青龙下无 config.json 时用于覆盖默认值）
ENV_CONFIG_MAP = {
    "BILI_TASKS": "tasks",
    "BILI_WATCH": "is_watch_video",
    "BILI_SHARE": "is_share_video",
    "BILI_NUMBER_OF_COINS": "number_of_coins",
    "BILI_PROTECTED_COINS": "number_of_protected_coins",
    "BILI_SELECT_LIKE": "select_like",
    "BILI_SAVE_COINS_LV6": "save_coins_when_lv6",
    "BILI_SUPPORT_UP_IDS": "support_up_ids",
    "BILI_SILVER2COIN": "is_silver2coin",
    "BILI_DEVICE_PLATFORM": "device_platform",
    "BILI_COMIC_ID": "custom_comic_id",
    "BILI_EP_ID": "custom_ep_id",
    "BILI_INTERVAL": "interval_seconds_between_request_api",
    "BILI_RANDOM_SLEEP": "random_sleep_max_min",
    "BILI_TICKET": "enable_bili_ticket",
    "BILI_PROXY": "web_proxy",
    "BILI_UA": "user_agent",
    "BILI_LOTTERY": "enable_lottery",
    "BILI_FANS_MEDAL": "enable_fans_medal",
    "BILI_LIKE_NUMBER": "fans_medal_like_number",
    "BILI_HEARTBEAT_NUMBER": "fans_medal_heartbeat_number",
    "BILI_PERSIST": "persist_cookies",
}

_TRUE = ("1", "true", "yes", "on")


def env_config_overrides(cfg: dict) -> dict:
    """将 BILI_* 环境变量合并进配置（环境变量优先于 config.json）。"""
    out = dict(cfg)
    for env_key, cfg_key in ENV_CONFIG_MAP.items():
        raw = get_env(env_key)
        if raw is None or raw.strip() == "":
            continue
        raw = raw.strip()
        default = cfg.get(cfg_key)
        if isinstance(default, bool):
            out[cfg_key] = raw.lower() in _TRUE
        elif isinstance(default, int):
            try:
                out[cfg_key] = int(float(raw))
            except ValueError:
                logger_warn(f"环境变量 {env_key}={raw} 不是有效数字，忽略")
        elif isinstance(default, list):
            out[cfg_key] = [x.strip() for x in raw.split(",") if x.strip()]
        else:
            out[cfg_key] = raw
    # 青龙环境变量合并
    ql = ql_env_config()
    for k, v in ql.items():
        if v:
            out[k] = v
    return out


def logger_warn(msg):
    try:
        from . import logger

        logger.warn(msg)
    except Exception:  # noqa: BLE001
        print(f"[warn] {msg}")


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path=None) -> dict:
    path = path or CONFIG_FILE
    if not os.path.exists(path):
        example = EXAMPLE_FILE if os.path.exists(EXAMPLE_FILE) else None
        if example:
            with open(example, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        else:
            cfg = {}
        save_config(cfg, path)
        print(f"[config] 已生成配置文件：{path}，请填入 cookies 后重新运行")
        return _deep_merge(DEFAULT_CONFIG, cfg)
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return _deep_merge(DEFAULT_CONFIG, cfg)


def save_config(cfg: dict, path=None):
    path = path or CONFIG_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def update_cookie_in_config(cfg: dict, account, path=None):
    """将补齐了设备身份的 cookie 写回配置（按 uid 匹配，找不到则追加）。"""
    if not cfg.get("persist_cookies", True):
        return False
    new_str = account.to_cookie_str()
    cookies = cfg.get("cookies") or []
    uid = account.uid
    for i, ck in enumerate(cookies):
        if f"DedeUserID={uid}" in (ck or ""):
            if ck == new_str:
                return False
            cookies[i] = new_str
            save_config(cfg, path)
            return True
    cookies.append(new_str)
    cfg["cookies"] = cookies
    save_config(cfg, path)
    return True
