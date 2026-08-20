# -*- coding: utf-8 -*-
"""二维码登录（参考 PiliPlusX 的 TV/APP 端扫码登录）。

与官方 Web passport 登录不同，PiliPlusX 使用 TV 端点扫码（app 风格）：
- 登录会话使用独立的设备身份（buvid + local_id），与后续业务身份隔离，更风控友好；
- 请求参数带 APP 签名（appkey + ts + sign，MD5）。

流程：
1. 生成本次登录会话的设备和身份（buvid/local_id/trace_id...）
2. POST /x/passport-tv-login/qrcode/auth_code 申请二维码（参数 AppSign）
3. 控制台打印二维码，等待扫码
4. POST /x/passport-tv-login/qrcode/poll 轮询，成功后在 Set-Cookie 中拿到
   SESSDATA / bili_jct / DedeUserID 等 cookie
"""
import hashlib
import random
import string
import time
from urllib.parse import quote

import requests

# ---- android_hd APP 凭据（PiliPlusX Constants） ----
APP_KEY = "dfca71928277209b"
APP_SEC = "b5475a8825547a4fc26c7d518eaaa02e"
MOBI_APP = "android_hd"
PLATFORM = "android"

# android_hd UA（PiliPlusX Constants.userAgent）
APP_UA = (
    "Mozilla/5.0 BiliDroid/2.0.1 (bbcallen@gmail.com) os/android "
    "model/android_hd mobi_app/android_hd build/2001100 channel/master "
    "innerVer/2001100 osVer/15 network/2"
)

PASSPORT_BASE = "https://passport.bilibili.com"
AUTH_CODE_URL = PASSPORT_BASE + "/x/passport-tv-login/qrcode/auth_code"
POLL_URL = PASSPORT_BASE + "/x/passport-tv-login/qrcode/poll"

# 设备档案（PiliPlusX AppDeviceProfiles.androidHd：Xiaomi 23046RP50C / Android 15）
DEVICE_MODEL = "23046RP50C"
DEVICE_BRAND = "Xiaomi"
DEVICE_OSVER = "15"
DEVICE_PLATFORM = f"Android{DEVICE_OSVER}{DEVICE_MODEL}"

_LOGIN_SCOPE = "login-session"
_ALNUM = string.ascii_letters + string.digits
_HEX = "0123456789abcdef"
_HEX_UPPER = "0123456789ABCDEF"


# ------------------------------------------------------------------ 身份生成
def gen_buvid(owner_key: str = "workflow:login-session", prefix: str = "XY") -> str:
    """PiliPlusX generateBuvidForOwner：md5 派生，37 位大写。"""
    normalized = "".join(c for c in owner_key if c.isalnum()).upper()
    digest = hashlib.md5(normalized.encode()).hexdigest().upper()
    return f"{prefix}{digest[2]}{digest[12]}{digest[22]}{digest}"


def _sha256_seed(label: str) -> bytes:
    return hashlib.sha256(label.encode()).digest()


def _bcd(value: int) -> int:
    return ((value // 10) << 4) | (value % 10)


def _pseudo_timestamp(seed: bytes):
    year = 2020 + seed[0] % 10
    month = 1 + seed[1] % 12
    day = 1 + seed[2] % 28
    return (year, month, day, seed[3] % 24, seed[4] % 60, seed[5] % 60)


def _encode_bcd_ts(ts):
    year, month, day, hh, mi, ss = ts
    return bytes(
        [_bcd(year // 100), _bcd(year % 100), _bcd(month), _bcd(day),
         _bcd(hh), _bcd(mi), _bcd(ss)]
    )


def _paired_hex_checksum(raw: str) -> str:
    norm = raw.lower()
    total = 0
    bounded = min(len(norm) - len(norm) % 2, 62)
    for i in range(0, bounded, 2):
        total += int(norm[i:i + 2], 16)
    return f"{total % 256:02x}"


def gen_device_local_id(owner_key: str, buvid: str) -> str:
    """PiliPlusX generateDeviceLocalId：34 位小写 hex。"""
    seed = _sha256_seed(f"device-local:{owner_key}:{buvid.upper()}")
    bcd = _encode_bcd_ts(_pseudo_timestamp(seed))
    payload = seed[:16] + bcd + seed[16:24]
    digest = hashlib.md5(payload).hexdigest()
    return digest + _paired_hex_checksum(digest)


def gen_session_id(length: int = 8) -> str:
    return "".join(random.choice(_ALNUM) for _ in range(length))


def gen_trace_id(now: int | None = None) -> str:
    """PiliPlusX generateTraceId：32:16:0:0 格式。"""
    ts = int(now or time.time())
    stamp = f"{ts >> 8:x}".zfill(6)[:6]
    body = "".join(random.choice(_ALNUM) for _ in range(24)) + stamp + \
        "".join(random.choice(_ALNUM) for _ in range(2))
    return f"{body}:{body[16:32]}:0:0"


class LoginIdentity:
    """一次扫码登录会话的独立设备身份（PiliPlusX createLoginSessionIdentity 等效）。"""

    def __init__(self, scope: str = _LOGIN_SCOPE):
        self.owner_key = f"workflow:{scope}"
        self.buvid = gen_buvid(self.owner_key)
        self.local_id = gen_device_local_id(self.owner_key, self.buvid)
        self.trace_id = gen_trace_id()
        self.session_id = gen_session_id()
        self.device_name = DEVICE_MODEL
        self.device_platform = DEVICE_PLATFORM
        self.bili_local_id = self.local_id
        self.device_id = self.local_id


# ------------------------------------------------------------------ APP 签名
def app_sign(params: dict, appkey: str = APP_KEY, appsec: str = APP_SEC) -> dict:
    """PiliPlusX AppSign：升序 + md5(query + appsec)。返回追加 appkey/ts/sign 的新 dict。"""
    p = dict(params)
    p["appkey"] = appkey
    p["ts"] = str(int(time.time()))
    items = sorted(p.items())
    query = "&".join(
        f"{quote(str(k), safe='')}={quote(str(v), safe='')}" for k, v in items
    )
    p["sign"] = hashlib.md5((query + appsec).encode()).hexdigest()
    return p


def _app_headers(identity: LoginIdentity) -> dict:
    return {
        "User-Agent": APP_UA,
        "buvid": identity.buvid,
        "env": "prod",
        "app-key": MOBI_APP,
        "x-bili-trace-id": identity.trace_id,
        "bili-http-engine": "cronet",
        "Accept": "application/json, text/plain, */*",
    }


# ------------------------------------------------------------------ 扫码流程
class TvLogin:
    """TV/APP 端点二维码登录。"""

    def __init__(self, identity: LoginIdentity | None = None, timeout: int = 20):
        self.identity = identity or LoginIdentity()
        self.session = requests.Session()
        self.session.headers.update(_app_headers(self.identity))
        self.timeout = timeout

    def generate(self) -> dict:
        """申请二维码，返回 {'auth_code', 'url'}。"""
        params = app_sign(
            {"local_id": self.identity.local_id, "platform": PLATFORM,
             "mobi_app": MOBI_APP}
        )
        r = self.session.post(AUTH_CODE_URL, params=params, timeout=self.timeout)
        j = r.json()
        if j.get("code") != 0:
            raise RuntimeError(f"申请二维码失败：{j.get('message')}")
        data = j.get("data") or {}
        return {"auth_code": data["auth_code"], "url": data["url"]}

    def poll(self, auth_code: str) -> dict:
        """轮询扫码结果。返回 {'status': bool, 'code': int, 'msg': str}。"""
        params = app_sign(
            {"auth_code": auth_code, "local_id": self.identity.local_id}
        )
        r = self.session.post(POLL_URL, params=params, timeout=self.timeout)
        j = r.json()
        code = j.get("code")
        msg = j.get("message")
        return {"status": code == 0, "code": code, "msg": msg}

    def extract_cookie(self) -> str:
        """从成功登录后的 session cookie 提取可用于后续业务的 cookie 字符串。"""
        wanted = [
            "SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5",
            "sid", "buvid3", "b_3", "b_4", "LIVE_BUVID", "b_nut",
        ]
        parts = []
        for ck in self.session.cookies:
            if ck.name in wanted and ck.value:
                parts.append(f"{ck.name}={ck.value}")
        return "; ".join(parts)
