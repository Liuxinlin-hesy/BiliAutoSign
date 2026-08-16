# -*- coding: utf-8 -*-
"""风控与签名工具。

- WBI 签名（含 PiliPlusX 同款 Web 端风控指纹参数 dm_img_*，缺失会触发 -352/-412）
- buvid3 / buvid4 获取（api.bilibili.com/x/frontend/finger/spi）
- bili_ticket 获取（GenWebTicket，hmac_sha256；非必需但可降低风控概率）

参考：
- https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign/wbi.md
- https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign/bili_ticket.md
- https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/buvid3_4.md
- PiliPlusX lib/utils/wbi_sign.dart（dm_img_* 指纹参数）
"""
import hashlib
import hmac
import random
import re
import time
from urllib.parse import quote, urlparse

# WBI 重排映射表（bilibili-API-collect / BiliBiliToolPro 一致）
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

# Web 端风控指纹参数（PiliPlusX wbi_sign.dart appendRiskFingerprintParams 同款，
# 参与 w_rid 签名计算，缺失会触发 -352 / -412 风控）
RISK_FINGERPRINT_PARAMS = {
    "dm_img_list": "[]",
    "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
    "dm_cover_img_str": (
        "QU5HTEUgKE5WSURJQSwgTlZJRElBIEdlRm9yY2UgR1RYIDEwNjAgNkdCIERpcmVjdDNEMTEg"
        "dnNfNV8wIHBzXzVfMCwgRDNEMTEp"
    ),
    "dm_img_inter": '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}',
}

# bili_ticket 接口参数（bilibili-API-collect docs/misc/sign/bili_ticket.md）
TICKET_HMAC_KEY = "XgwSnGZ1p"
TICKET_URL = "https://api.bilibili.com/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket"

# buvid3/4 获取
FINGER_SPI_URL = "https://api.bilibili.com/x/frontend/finger/spi"

_CHR_FILTER = re.compile(r"[!'()*]")
_ALPHABET_HEX = "0123456789ABCDEF"


def get_mixin_key(raw_wbi_key: str) -> str:
    """对 img_key + sub_key 做重排，截取前 32 位。"""
    return "".join(raw_wbi_key[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def enc_wbi(params: dict, mixin_key: str) -> dict:
    """为请求参数进行 WBI 签名（含风控指纹参数），返回追加了 wts/w_rid 的新 dict。"""
    p = dict(params)
    # 追加 Web 端风控指纹参数；已存在则不覆盖（允许调用方自定义）
    for k, v in RISK_FINGERPRINT_PARAMS.items():
        p.setdefault(k, v)
    p["wts"] = int(time.time())
    # 过滤 value 中的 "!'()*" 字符，再按 key 升序排序
    items = sorted(
        (str(k), _CHR_FILTER.sub("", str(v))) for k, v in p.items()
    )
    query = "&".join(f"{quote(k)}={quote(v)}" for k, v in items)
    p["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return p


def wbi_key_from_url(url: str) -> str:
    """从 wbi_img 的 png url 中提取 key（文件名，不含扩展名）。"""
    name = urlparse(url).path.rsplit("/", 1)[-1]
    return name.split(".")[0]


def gen_buvid3() -> str:
    """本地生成 buvid3 兜底：32 位大写十六进制 + 5 位数字 + infoc。"""
    return "".join(random.choice(_ALPHABET_HEX) for _ in range(32)) + \
        "".join(random.choice("0123456789") for _ in range(5)) + "infoc"


def calc_ticket_hexsign(ts: int) -> str:
    """bili_ticket hexsign = hmac_sha256(key='XgwSnGZ1p', msg='ts<timestamp>')"""
    return hmac.new(
        TICKET_HMAC_KEY.encode(), f"ts{ts}".encode(), hashlib.sha256
    ).hexdigest()
