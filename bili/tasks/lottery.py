# -*- coding: utf-8 -*-
"""天选时刻抽奖（可选，默认关闭）。

对应 BiliBiliToolPro LiveDomainService.TianXuan：
- 扫描直播分区 → 查找带“天选时刻”挂件(504)的直播间
- CheckTianXuan 校验 → Join 参与
仅参与无需赠礼、无粉丝牌要求、最多要求关注的天选抽奖。
"""
import random

from .. import logger
from .base import Task, TaskResult, register

AREA_LIST_URL = "https://api.live.bilibili.com/xlive/web-interface/v1/index/getWebAreaList"
GET_LIST_URL = "https://api.live.bilibili.com/xlive/web-interface/v1/second/getList"
CHECK_URL = "https://api.live.bilibili.com/xlive/lottery-interface/v1/Anchor/Check"
JOIN_URL = "https://api.live.bilibili.com/xlive/lottery-interface/v1/Anchor/Join"

PENDANT_ID_TIANXUAN = 504
MAX_PAGES = 3  # 每分区扫描页数（BiliBiliToolPro 为 5，保守起见默认 3）


@register
class LotteryTask(Task):
    name = "lottery"
    title = "天选时刻抽奖（可选）"

    def run(self, client):
        self.tag = client.tag
        result = TaskResult(self.name)
        if client.risk_limited:
            self.log_warn("账号风控受限，跳过天选抽奖")
            return result

        areas = self.safe(self.get_areas, client)
        if not areas:
            self.log_warn("获取直播分区失败")
            return result

        joined = 0
        scanned = 0
        for area in areas:
            if client.risk_limited:
                break
            for page in range(1, MAX_PAGES + 1):
                rooms = self.safe(self.get_list, client, area.get("id"), page)
                if not rooms:
                    break
                for room in rooms:
                    scanned += 1
                    if self.safe(self.try_join, client, room):
                        joined += 1
                    if client.risk_limited:
                        break
                if len(rooms) < 40:
                    break
        self.log(f"扫描直播间 {scanned} 个，成功参与天选抽奖 {joined} 个")
        result.ok = joined
        if scanned == 0:
            result.fail = 1
        return result

    def get_areas(self, client):
        j = client.get(
            AREA_LIST_URL,
            params={"source_id": 2},
            referer="https://live.bilibili.com/",
        )
        data = j.get("data") or {}
        areas = []
        for grp in data.values():
            if not isinstance(grp, dict):
                continue
            for item in grp.get("list") or []:
                if isinstance(item, dict) and item.get("id"):
                    areas.append(item)
        return areas

    def get_list(self, client, area_id, page):
        j = client.get(
            GET_LIST_URL,
            params={
                "platform": "web",
                "parent_area_id": area_id,
                "area_id": 0,
                "sort_type": "",
                "page": page,
            },
            referer="https://live.bilibili.com/",
        )
        data = j.get("data") or {}
        return data.get("list") or []

    def try_join(self, client, room):
        pendant = room.get("pendant_info") or {}
        p = pendant.get("2") if isinstance(pendant, dict) else None
        if not p or p.get("pendent_id") != PENDANT_ID_TIANXUAN:
            return False

        roomid = room.get("roomid")
        check = client.get(CHECK_URL, params={"roomid": roomid},
                           referer="https://live.bilibili.com/")
        info = check.get("data")
        if not info or info.get("status") != 0:
            return False
        # 仅参与：无需赠礼、无粉丝牌要求、最多要求关注
        if info.get("gift_price", 0) > 0:
            return False
        if info.get("require_type") not in (0, 2):  # 0=无要求 2=关注
            return False

        data = {
            "id": info.get("id"),
            "gift_id": info.get("gift_id", 0),
            "gift_num": info.get("gift_num", 0),
            "csrf": client.account.csrf,
        }
        j = client.post(
            JOIN_URL,
            data=data,
            referer=f"https://live.bilibili.com/{roomid}",
        )
        if j.get("code") == 0:
            self.log(f"参与天选抽奖成功：{room.get('title', '?')}（奖品：{info.get('award_name', '?')}）")
            return True
        self.log(f"参与天选抽奖失败：{j.get('message') or j.get('msg')}")
        return False
