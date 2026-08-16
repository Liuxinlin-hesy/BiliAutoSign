# -*- coding: utf-8 -*-
"""青龙面板通知：通过青龙 OpenAPI 推送运行结果摘要。

- 获取 token：POST {ql_base_url}/open/auth/token?client_id=..&client_secret=..
- 推送通知：POST {ql_base_url}/open/push?title=..&content=..  （Authorization: Bearer <token>）

凭据来源（优先级从高到低）：
1. 环境变量 QL_CLIENT_ID / QL_CLIENT_SECRET / QL_BASE_URL（青龙推荐）
2. config.json 的 ql_client_id / ql_client_secret / ql_base_url
"""
import json

import requests

from . import logger

DEFAULT_QL_BASE = "http://127.0.0.1:5600"


def _ql_base(cfg) -> str:
    base = (cfg.get("ql_base_url") or "").strip().rstrip("/")
    return base or DEFAULT_QL_BASE


def send_qinglong_notify(cfg, title: str, content: str) -> bool:
    """发送青龙通知；未配置凭据或发送失败时返回 False（不抛异常）。"""
    client_id = (cfg.get("ql_client_id") or "").strip()
    client_secret = (cfg.get("ql_client_secret") or "").strip()
    if not client_id or not client_secret:
        logger.debug("未配置青龙 OpenAPI 凭据（QL_CLIENT_ID/QL_CLIENT_SECRET），跳过通知")
        return False
    base = _ql_base(cfg)
    try:
        r = requests.post(
            f"{base}/open/auth/token",
            params={"client_id": client_id, "client_secret": client_secret},
            timeout=10,
        )
        data = r.json().get("data") or {}
        token = data.get("token")
        if not token:
            logger.warn(f"青龙获取 token 失败：{r.text[:200]}")
            return False
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.post(
            f"{base}/open/push",
            params={"title": title, "content": content},
            headers=headers,
            timeout=10,
        )
        if r.status_code == 200:
            logger.info("青龙通知已发送")
            return True
        logger.warn(f"青龙通知发送失败：HTTP {r.status_code} {r.text[:200]}")
        return False
    except requests.RequestException as e:
        logger.warn(f"青龙通知发送异常（不影响任务结果）：{e}")
        return False


def build_summary(rows, names) -> str:
    """构造运行结果摘要文本。rows: (uid, ok, fail, notes)"""
    lines = [f"任务：{', '.join(names)}"]
    for uid, okc, failc, _notes in rows:
        status = "OK" if failc == 0 else "异常"
        lines.append(f"[{uid}] {status} 成功 {okc} / 失败 {failc}")
    return "\n".join(lines)
