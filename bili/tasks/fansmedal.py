# -*- coding: utf-8 -*-
"""粉丝勋章任务（可选，默认关闭）：点赞直播间 + 直播心跳。

对应 BiliBiliToolPro LiveFansMedalAppService：
- MedalWall 获取有粉丝牌的直播间
- 点赞：/xlive/app-ucenter/v1/like_info_v3/like/likeReportV3
- 心跳：/xlive/data-interface/v1/x25Kn/E（进房）+ /xlive/data-interface/v1/x25Kn/X（心跳）
"""
import random
import time
import uuid

from .. import logger
from .base import Task, TaskResult, register

MEDAL_WALL_URL = "https://api.live.bilibili.com/xlive/web-ucenter/user/MedalWall"
LIKE_URL = "https://api.live.bilibili.com/xlive/app-ucenter/v1/like_info_v3/like/likeReportV3"
ENTER_ROOM_URL = "https://api.live.bilibili.com/xlive/data-interface/v1/x25Kn/E"
HEARTBEAT_URL = "https://api.live.bilibili.com/xlive/data-interface/v1/x25Kn/X"
ROOM_INFO_URL = "https://api.live.bilibili.com/room/v1/Room/get_info"
SPACE_INFO_URL = "https://api.bilibili.com/x/space/wbi/acc/info"


@register
class FansMedalTask(Task):
    name = "fansmedal"
    title = "粉丝勋章（点赞/心跳，可选）"

    def run(self, client):
        self.tag = client.tag
        result = TaskResult(self.name)
        if client.risk_limited:
            self.log_warn("账号风控受限，跳过粉丝勋章任务")
            return result

        like_num = int(self.opts.get("fans_medal_like_number", 5))
        hb_num = int(self.opts.get("fans_medal_heartbeat_number", 30))

        medals = self.safe(self.get_medals, client)
        if not medals:
            self.log("未获取到粉丝勋章")
            return result

        live_rooms = []
        for medal in medals:
            room = self.safe(self.get_live_room, client, medal)
            if room:
                live_rooms.append(room)

        live = [r for r in live_rooms if r.get("live_status") != 0]
        self.log(f"共 {len(live_rooms)} 个有粉丝牌的直播间，其中开播 {len(live)} 个")

        if like_num > 0:
            for room in live[:3]:
                self.like_room(client, room, like_num, result)
                time.sleep(random.uniform(5, 8))
        if hb_num > 0:
            for room in live[:1]:
                self.heartbeat_room(client, room, hb_num, result)
        return result

    def get_medals(self, client):
        j = client.get(
            MEDAL_WALL_URL,
            params={"target_id": client.account.uid},
            referer="https://live.bilibili.com/",
        )
        return (j.get("data") or {}).get("list") or []

    def get_live_room(self, client, medal):
        medal_info = medal.get("medal_info") or {}
        target_id = medal_info.get("target_id")
        if not target_id:
            return None
        j = client.get(
            SPACE_INFO_URL,
            params={"mid": target_id},
            wbi=True,
            referer=f"https://space.bilibili.com/{target_id}",
            origin="https://space.bilibili.com",
        )
        data = j.get("data") or {}
        live_room = data.get("live_room") or {}
        roomid = live_room.get("roomid")
        if not roomid:
            return None
        info = client.get(
            ROOM_INFO_URL,
            params={"room_id": roomid, "from": "room"},
            referer="https://live.bilibili.com/",
        )
        room = (info.get("data") or {})
        return {
            "roomid": roomid,
            "uid": room.get("uid"),
            "live_status": room.get("live_status", 0),
            "parent_area_id": room.get("parent_area_id", 0),
            "area_id": room.get("area_id", 0),
            "title": medal.get("target_name", ""),
        }

    def like_room(self, client, room, like_num, result):
        data = {
            "room_id": room["roomid"],
            "csrf": client.account.csrf,
            "up_uid": room.get("uid") or 0,
            "uid": client.account.uid,
            "click_time": like_num,
        }
        j = client.post(
            LIKE_URL,
            data=data,
            referer=f"https://live.bilibili.com/{room['roomid']}",
        )
        if j.get("code") == 0:
            self.log(f"点赞直播间 {room['roomid']} 完成（{like_num} 次）")
            result.ok += 1
        else:
            self.log_warn(f"点赞直播间 {room['roomid']} 失败：{j.get('message') or j.get('msg')}")

    def heartbeat_room(self, client, room, hb_num, result):
        buvid = client.account.get("buvid3", "")
        ts = int(time.time() * 1000)
        e_headers = {"User-Agent": client.ua}
        j = client.post(
            ENTER_ROOM_URL,
            data={
                "platform": "web",
                "uuid": str(uuid.uuid4()),
                "buid": buvid,
                "room_id": room["roomid"],
                "parent_area_id": room["parent_area_id"],
                "area_id": room["area_id"],
                "seq_id": 1,
                "room_type": 0,
                "timestamp": ts,
                "rtime": ts,
                "uids": f'["{client.account.uid}","{str(uuid.uuid4())}"]',
                "csrf": client.account.csrf,
                "real_room_id": room["roomid"],
                "biz": 1,
            },
            referer=f"https://live.bilibili.com/{room['roomid']}",
        )
        if j.get("code") != 0:
            self.log_warn(f"进房心跳失败：{j.get('message') or j.get('msg')}")
            return
        secret_key = ""
        secret_rule = 0
        success = 0
        for i in range(1, hb_num + 1):
            data = {
                "platform": "web",
                "uuid": str(uuid.uuid4()),
                "buid": buvid,
                "room_id": room["roomid"],
                "parent_area_id": room["parent_area_id"],
                "area_id": room["area_id"],
                "seq_id": i + 1,
                "room_type": 0,
                "timestamp": int(time.time() * 1000),
                "rtime": int(time.time() * 1000),
                "uids": f'["{client.account.uid}","{str(uuid.uuid4())}"]',
                "csrf": client.account.csrf,
                "secret_key": secret_key,
                "secret_rule": secret_rule,
                "real_room_id": room["roomid"],
                "biz": 1,
            }
            j = client.post(
                HEARTBEAT_URL,
                data=data,
                referer=f"https://live.bilibili.com/{room['roomid']}",
            )
            if j.get("code") == 0:
                success += 1
                d = j.get("data") or {}
                secret_key = d.get("secret_key", secret_key)
                secret_rule = d.get("secret_rule", secret_rule)
            time.sleep(30)
        self.log(f"直播间 {room['roomid']} 心跳完成 {success}/{hb_num}")
        result.ok += 1 if success else 0
