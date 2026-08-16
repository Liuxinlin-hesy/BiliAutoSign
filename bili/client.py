# -*- coding: utf-8 -*-
"""BiliClient —— 带风控策略的 B 站 HTTP 客户端。

风控策略（参考 BiliBiliToolPro 的 IntervalDelegatingHandler / SecurityOptions，
以及 PiliPlusX 的请求头与指纹策略）：
1. 设备身份：自动获取 buvid3 / buvid4（finger/spi），可选 bili_ticket（GenWebTicket，
   有效期 3 天，可显著降低风控概率）；
2. WBI 签名：需要签名的接口自动携带 w_rid/wts，签名参数中包含 Web 端风控指纹
   dm_img_*（PiliPlusX 同款），避免 -352/-412；
3. 请求节奏：每次 API 调用前随机休眠 [interval/2, interval] 秒，避免短时高频请求；
4. 失败策略：网络错误 / 5xx 自动重试（带抖动退避）；业务错误不重试；
5. 风控熔断：遇到 -412 / -352 时标记账号为“风控受限”，后续写操作跳过并提示。
"""
import random
import time
from urllib.parse import urlparse

import requests

from . import logger, risk
from .account import Account

# 各主机默认 Referer / Origin（与 BiliBiliToolPro 的 Header 属性一致）
HOST_DEFAULTS = {
    "api.bilibili.com": ("https://www.bilibili.com/", "https://www.bilibili.com"),
    "api.live.bilibili.com": ("https://live.bilibili.com/", None),
    "manga.bilibili.com": ("https://manga.bilibili.com/", "https://manga.bilibili.com"),
    "account.bilibili.com": ("https://account.bilibili.com/account/home",
                             "https://account.bilibili.com"),
    "big.bilibili.com": ("https://big.bilibili.com/mobile/bigPoint/task", None),
    "api.vc.bilibili.com": ("https://live.bilibili.com/", None),
}

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# 触发风控熔断的业务码
RISK_CODES = (-412, -352)


class BiliRequestError(Exception):
    def __init__(self, message, code=None, http_status=None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class BiliClient:
    def __init__(self, account: Account, opts: dict):
        self.account = account
        self.opts = opts
        self.interval = max(0, float(opts.get("interval_seconds_between_request_api", 3)))
        self.timeout = float(opts.get("timeout", 20))
        self.retries = int(opts.get("retries", 2))
        self.enable_ticket = bool(opts.get("enable_bili_ticket", True))
        self.ua = opts.get("user_agent") or DEFAULT_UA
        self.proxy = opts.get("web_proxy") or None

        self.session = requests.Session()
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}
        self.session.headers.update({
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        })
        self._wbi_keys = None          # (img_key, sub_key, fetch_ts)
        self._device_ready = False
        self.risk_limited = False      # 风控熔断标记
        self._last_request_ts = 0.0

    # ------------------------------------------------------------------ 设备身份
    def ensure_device(self):
        """补齐设备身份：buvid3/buvid4 + bili_ticket + WBI keys。幂等。"""
        if self._device_ready:
            return
        self._device_ready = True
        try:
            self._ensure_buvid()
        except Exception as e:
            logger.debug(f"初始化 buvid 失败（继续运行）：{e}")
        try:
            self._ensure_ticket()
        except Exception as e:
            logger.debug(f"获取 bili_ticket 失败（继续运行）：{e}")
        try:
            self._ensure_wbi_keys()
        except Exception as e:
            logger.debug(f"获取 WBI keys 失败（继续运行）：{e}")

    def _ensure_buvid(self):
        if self.account.get("buvid3") or self.account.get("b_3"):
            return
        r = self.session.get(risk.FINGER_SPI_URL, timeout=self.timeout)
        data = r.json().get("data") or {}
        b3 = data.get("b_3")
        b4 = data.get("b_4")
        if b3:
            self.account.set("buvid3", b3)
            self.account.set("b_3", b3)
            if b4:
                self.account.set("b_4", b4)
            logger.debug(f"[{self.tag}] 已获取 buvid3/4")
        else:
            self.account.set("buvid3", risk.gen_buvid3())
            logger.debug(f"[{self.tag}] buvid3 接口异常，使用本地生成兜底")

    def _ensure_ticket(self):
        if not self.enable_ticket:
            return
        now = int(time.time())
        exp = self.account.get("bili_ticket_expires", "0")
        if self.account.get("bili_ticket") and exp.isdigit() and now < int(exp) - 600:
            return
        ts = int(time.time())
        params = {
            "key_id": "ec02",
            "hexsign": risk.calc_ticket_hexsign(ts),
            "context[ts]": str(ts),
            "csrf": self.account.csrf,
        }
        r = self.session.post(risk.TICKET_URL, params=params, timeout=self.timeout)
        data = r.json().get("data") or {}
        ticket = data.get("ticket")
        if ticket:
            self.account.set("bili_ticket", ticket)
            self.account.set("bili_ticket_expires", str(ts + int(data.get("ttl", 259200))))
            logger.debug(f"[{self.tag}] 已刷新 bili_ticket（有效期 {data.get('ttl', 259200)}s）")
            # ticket 响应也携带 wbi keys，可直接缓存
            nav = data.get("nav") or {}
            if nav.get("img") and nav.get("sub"):
                self._wbi_keys = (
                    risk.wbi_key_from_url(nav["img"]),
                    risk.wbi_key_from_url(nav["sub"]),
                    time.time(),
                )

    def _ensure_wbi_keys(self):
        if self._wbi_keys and time.time() - self._wbi_keys[2] < 86400:
            return
        keys = None
        # 优先从 nav（需要登录态）获取
        try:
            j = self.request_raw(
                "GET", "https://api.bilibili.com/x/web-interface/nav",
                skip_interval=True, skip_risk=True,
            )
            wbi = (j.get("data") or {}).get("wbi_img") or {}
            if wbi.get("img_url") and wbi.get("sub_url"):
                keys = (risk.wbi_key_from_url(wbi["img_url"]),
                        risk.wbi_key_from_url(wbi["sub_url"]))
        except Exception:
            keys = None
        if keys:
            self._wbi_keys = (keys[0], keys[1], time.time())
            logger.debug(f"[{self.tag}] WBI keys 已就绪")

    def get_wbi_keys(self):
        self.ensure_device()
        if not self._wbi_keys:
            raise BiliRequestError("无法获取 WBI keys（nav 与 ticket 均失败）")
        return self._wbi_keys

    # ------------------------------------------------------------------ 请求核心
    @property
    def tag(self):
        return f"账号 {self.account.uid}" if self.account.uid else "账号"

    def _cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self.account.cookies.items() if v)

    def _sleep_interval(self):
        if self.interval <= 0:
            return
        low = self.interval / 2
        high = self.interval
        wait = random.uniform(low, high)
        time.sleep(wait)

    def _host_headers(self, url: str):
        host = urlparse(url).netloc.split(":")[0]
        referer, origin = HOST_DEFAULTS.get(host, ("https://www.bilibili.com/", None))
        headers = {"Referer": referer}
        if origin:
            headers["Origin"] = origin
        return headers

    def request_raw(self, method, url, params=None, data=None, json_body=None,
                    headers=None, skip_interval=False, skip_risk=False,
                    timeout=None):
        """底层请求：只负责发送 + 网络层重试，返回 JSON dict。"""
        method = method.upper()
        if not skip_interval:
            self._sleep_interval()
        hdrs = self._host_headers(url)
        if headers:
            hdrs.update(headers)
        hdrs["Cookie"] = self._cookie_header()

        last_exc = None
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.request(
                    method, url, params=params, data=data, json=json_body,
                    headers=hdrs, timeout=timeout or self.timeout,
                )
                if resp.status_code >= 500:
                    raise BiliRequestError(f"HTTP {resp.status_code}", http_status=resp.status_code)
                try:
                    j = resp.json()
                except ValueError:
                    raise BiliRequestError(
                        f"响应不是 JSON（HTTP {resp.status_code}）",
                        http_status=resp.status_code,
                    )
                code = j.get("code")
                if not skip_risk and code in RISK_CODES:
                    self.risk_limited = True
                    logger.error(
                        f"[{self.tag}] 触发风控（code={code}，{j.get('message') or j.get('msg')}）"
                        f"，已标记该账号为风控受限，本次运行将跳过后续写操作"
                    )
                return j
            except (requests.RequestException, BiliRequestError) as e:
                last_exc = e
                if attempt < self.retries:
                    wait = random.uniform(1.5, 3.0)
                    logger.debug(f"[{self.tag}] 请求失败（{e}），{wait:.1f}s 后重试 "
                                 f"({attempt + 1}/{self.retries})")
                    time.sleep(wait)
                else:
                    break
        raise BiliRequestError(f"请求失败: {last_exc}")

    def request(self, method, url, *, params=None, data=None, json_body=None,
                wbi=False, csrf=False, referer=None, origin=None, headers=None,
                skip_interval=False, skip_risk=False, extra=None):
        """带风控策略的业务请求。

        wbi: 对 params 做 WBI 签名（需登录态取 keys）
        csrf: 自动附加 bili_jct（GET→params，POST→form data）
        extra: 附加在 params 中的额外参数（WBI 签名时一并参与签名）
        """
        params = dict(params or {})
        data = dict(data or {})
        if extra:
            params.update(extra)
        if csrf:
            target = params if method.upper() == "GET" else data
            target["csrf"] = self.account.csrf
        if wbi:
            img_key, sub_key, _ = self.get_wbi_keys()
            params = risk.enc_wbi(params, risk.get_mixin_key(img_key + sub_key))
        hdrs = {}
        if referer:
            hdrs["Referer"] = referer
        if origin:
            hdrs["Origin"] = origin
        j = self.request_raw(method, url, params=params, data=data or None,
                             json_body=json_body, headers=hdrs,
                             skip_interval=skip_interval, skip_risk=skip_risk)
        return j

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    # ------------------------------------------------------------------ 常用封装
    def nav(self):
        """登录态 + 用户信息。code=-101 表示未登录。"""
        j = self.request_raw("GET", "https://api.bilibili.com/x/web-interface/nav",
                             skip_interval=True)
        return j

    def user_info(self) -> dict:
        j = self.nav()
        if j.get("code") != 0:
            raise BiliRequestError(f"登录校验失败: {j.get('message')}", code=j.get("code"))
        return j.get("data") or {}
