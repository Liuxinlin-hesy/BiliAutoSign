# -*- coding: utf-8 -*-
"""配置加载：config.json（不存在时从 config.example.json 自动生成）。"""
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
    # 其他
    "persist_cookies": True,
}


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
