# -*- coding: utf-8 -*-
"""漫画任务：每日签到 + 阅读（可选）+ 大会员漫读劵。

对应 BiliBiliToolPro：
- 签到：POST manga.bilibili.com/twirp/activity.v1.Activity/ClockIn?platform=android
- 阅读：POST /twirp/bookshelf.v1.Bookshelf/AddHistory?platform=..&comic_id=..&ep_id=..
- 大会员漫读劵：POST /twirp/user.v1.User/GetVipReward?reason_id=1
"""
from .. import logger
from .base import Task, TaskResult, register

MANGA_BASE = "https://manga.bilibili.com"
CLOCK_IN_URL = MANGA_BASE + "/twirp/activity.v1.Activity/ClockIn"
ADD_HISTORY_URL = MANGA_BASE + "/twirp/bookshelf.v1.Bookshelf/AddHistory"
GET_VIP_REWARD_URL = MANGA_BASE + "/twirp/user.v1.User/GetVipReward"


@register
class MangaTask(Task):
    name = "manga"
    title = "漫画任务（每日签到/阅读/大会员漫读劵）"

    def run(self, client):
        self.tag = client.tag
        result = TaskResult(self.name)
        if client.risk_limited:
            self.log_warn("账号风控受限，跳过漫画任务")
            return result

        platform = self.opts.get("device_platform", "android")
        self.clock_in(client, platform, result)
        self.read_manga(client, platform, result)
        self.get_vip_reward(client, result)
        return result

    def clock_in(self, client, platform, result):
        # 重复签到会返回 400/异常，按 BiliBiliToolPro 处理为“今日已签到”
        try:
            j = client.post(
                CLOCK_IN_URL,
                params={"platform": platform},
                json_body={},
                referer="https://manga.bilibili.com/",
                origin="https://manga.bilibili.com",
            )
        except Exception as e:  # noqa: BLE001
            self.log_warn(f"漫画签到：今日可能已签到过（{e}）")
            return
        if j.get("code") == 0:
            self.log("漫画签到成功")
            result.ok += 1
        else:
            msg = str(j.get("msg") or j.get("message") or j.get("code"))
            if "重复" in msg:
                self.log("漫画签到：今日已签到过")
            else:
                self.log(f"漫画签到失败：{msg}")
                result.fail += 1

    def read_manga(self, client, platform, result):
        comic_id = int(self.opts.get("custom_comic_id") or 0)
        ep_id = int(self.opts.get("custom_ep_id") or 0)
        if comic_id <= 0:
            return
        j = client.post(
            ADD_HISTORY_URL,
            params={"platform": platform, "comic_id": comic_id, "ep_id": ep_id},
            json_body={},
            referer="https://manga.bilibili.com/",
            origin="https://manga.bilibili.com",
        )
        if j.get("code") == 0:
            self.log("漫画阅读成功")
            result.ok += 1
        else:
            self.log_warn(f"漫画阅读失败：{j.get('msg') or j.get('message')}")

    def get_vip_reward(self, client, result):
        # 非大会员跳过（GetVipReward 需要大会员身份）
        try:
            user_info = client.user_info()
        except Exception:  # noqa: BLE001
            return
        if not (user_info.get("vip_status") and user_info.get("vipType") in (1, 2)):
            self.log("非大会员，跳过漫画漫读劵领取")
            return
        j = client.post(
            GET_VIP_REWARD_URL,
            params={"reason_id": 1},
            json_body={},
            referer="https://manga.bilibili.com/",
            origin="https://manga.bilibili.com",
        )
        if j.get("code") == 0:
            data = j.get("data") or {}
            self.log(f"领取大会员漫画权益成功：+{data.get('amount', '?')} 张漫读劵")
            result.ok += 1
        else:
            self.log(f"领取大会员漫画权益：{j.get('msg') or j.get('message')}")
