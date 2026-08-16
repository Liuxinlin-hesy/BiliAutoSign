# -*- coding: utf-8 -*-
"""账号：解析 cookie 字符串并校验完整性。"""
import re


class Account:
    """一个 B 站账号（一组 cookie）。"""

    REQUIRED = ("SESSDATA", "bili_jct", "DedeUserID")
    OPTIONAL = ("DedeUserID__ckMd5", "sid", "buvid3", "b_3", "b_4",
                "LIVE_BUVID", "bili_ticket", "bili_ticket_expires", "b_nut")

    def __init__(self, cookie_str: str, name: str = ""):
        self.cookie_str = cookie_str.strip()
        self.name = name or ""
        self.cookies = self._parse(cookie_str)
        self._extra = {}

    @staticmethod
    def _parse(cookie_str: str) -> dict:
        cookies = {}
        for part in cookie_str.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
        return cookies

    @property
    def uid(self) -> str:
        return self.cookies.get("DedeUserID", "")

    @property
    def csrf(self) -> str:
        return self.cookies.get("bili_jct", "")

    @property
    def sessdata(self) -> str:
        return self.cookies.get("SESSDATA", "")

    def get(self, key: str, default: str = "") -> str:
        return self.cookies.get(key, default)

    def set(self, key: str, value: str):
        self.cookies[key] = value
        if key not in self.cookies:
            self.cookies[key] = value

    def validate(self) -> list:
        """返回缺失项列表；空列表表示完整。"""
        missing = [k for k in self.REQUIRED if not self.cookies.get(k)]
        if missing:
            return [f"缺少必要 Cookie 项: {', '.join(missing)}"]
        if not re.fullmatch(r"\d+", self.uid):
            return [f"DedeUserID 不是有效数字: {self.uid}"]
        return []

    def to_cookie_str(self) -> str:
        """重新序列化为 cookie 字符串（保留原始顺序优先，新增项追加）。"""
        parts = []
        seen = set()
        for part in self.cookie_str.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k = part.split("=", 1)[0].strip()
            if k in seen:
                continue
            seen.add(k)
            parts.append(f"{k}={self.cookies.get(k, '')}")
        for k in self.OPTIONAL:
            if k not in seen and k in self.cookies:
                parts.append(f"{k}={self.cookies[k]}")
        return "; ".join(parts)

    def __str__(self):
        return f"Account(uid={self.uid}{', ' + self.name if self.name else ''})"
