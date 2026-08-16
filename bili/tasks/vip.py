# -*- coding: utf-8 -*-
"""大会员任务：每月福利（B币券/权益）+ 大会员大积分。

对应 BiliBiliToolPro：
- 每日任务中的“领取大会员福利”：/x/vip/privilege/receive（type=1 B币券，type=2 权益）
- VipBigPointAppService 大会员大积分：
  - 经验加速包：/x/vip/privilege/my 查 state，/x/vip/experience/add 兑换
  - 三日签到：/x/vip/vip_center/sign_in/three_days_sign + /pgc/activity/score/task/sign2
  - 任务列表：/x/vip_point/task/combine
  - 福利任务 bonus / 体验任务 privilege：receive/v2 + complete/v2
  - 日常任务：dress-view、vipmallview（show.bilibili.com 埋点）、
    animatetab/filmtab（deliver/task/complete）、ogvwatchnew
"""
import random
import time

from .. import logger
from .base import Task, TaskResult, register

VIP_PRIVILEGE_RECEIVE = "https://api.bilibili.com/x/vip/privilege/receive"
VIP_PRIVILEGE_MY = "https://api.bilibili.com/x/vip/privilege/my"
VIP_EXPERIENCE_ADD = "https://api.bilibili.com/x/vip/experience/add"
THREE_DAYS_SIGN = "https://api.bilibili.com/x/vip/vip_center/sign_in/three_days_sign"
SIGN2 = "https://api.bilibili.com/pgc/activity/score/task/sign2"
TASK_COMBINE = "https://api.bilibili.com/x/vip_point/task/combine"
TASK_RECEIVE_V2 = "https://api.bilibili.com/pgc/activity/score/task/receive/v2"
TASK_COMPLETE_V2 = "https://api.bilibili.com/pgc/activity/score/task/complete/v2"
TASK_DELIVER = "https://api.bilibili.com/pgc/activity/deliver/task/complete"
VIP_MALL_DISPATCH = "https://show.bilibili.com/api/activity/fire/common/event/dispatch"


@register
class VipBigPointTask(Task):
    name = "vip"
    title = "大会员任务（每月福利/大积分）"

    def run(self, client):
        self.tag = client.tag
        result = TaskResult(self.name)
        if client.risk_limited:
            self.log_warn("账号风控受限，跳过大会员任务")
            return result

        try:
            user_info = client.user_info()
        except Exception as e:  # noqa: BLE001
            self.log_err(f"获取用户信息失败：{e}")
            result.fail += 1
            return result

        is_vip = bool(user_info.get("vip_status")) and user_info.get("vipType") in (1, 2)
        if not is_vip:
            self.log("非大会员，跳过大会员任务")
            return result

        self.receive_monthly_privilege(client, result)
        self.big_point(client, result)
        return result

    # ------------------------------------------------------------- 每月福利
    def receive_monthly_privilege(self, client, result):
        for type_, name in ((1, "大会员 B币券"), (2, "大会员福利/权益")):
            j = client.post(
                VIP_PRIVILEGE_RECEIVE,
                params={"type": type_, "csrf": client.account.csrf},
                referer="https://account.bilibili.com/account/home",
                origin="https://account.bilibili.com",
            )
            if j.get("code") == 0:
                self.log(f"领取{name}成功")
                result.ok += 1
            else:
                self.log(f"领取{name}：{j.get('message') or j.get('msg')}")

    # ------------------------------------------------------------- 大积分
    def big_point(self, client, result):
        self.express(client, result)
        if client.risk_limited:
            return
        self.three_day_sign(client, result)
        combine = self.safe(self.get_combine, client)
        if not combine:
            self.log_warn("获取大积分任务列表失败，跳过任务")
            return
        self.log_task_modules(combine)
        self.one_time_mission(client, combine, "福利任务", "bonus", result)
        self.one_time_mission(client, combine, "体验任务", "privilege", result)
        if client.risk_limited:
            return
        self.daily_missions(client, combine, result)

    def express(self, client, result):
        j = client.get(VIP_PRIVILEGE_MY)
        items = ((j.get("data") or {}).get("list")) or []
        item = next((x for x in items if x.get("type") == 9), None)
        if item is None:
            self.log("未找到大会员经验加速包任务")
            return
        state = item.get("state")
        if state == 1:
            self.log("大会员经验已兑换")
            return
        if state == 2:
            self.log("大会员经验观看任务未完成，先观看一个视频")
            self.safe(self._watch_for_express, client)
            # 重新查询状态
            j = client.get(VIP_PRIVILEGE_MY)
            items = ((j.get("data") or {}).get("list")) or []
            item = next((x for x in items if x.get("type") == 9), None)
            state = item.get("state") if item else None
            if state != 0:
                self.log_warn("观看后仍未解锁经验兑换，跳过")
                return
        if state == 0:
            j = client.post(
                VIP_EXPERIENCE_ADD,
                data={"csrf": client.account.csrf},
                referer="https://big.bilibili.com/mobile/bigPoint/task",
            )
            if j.get("code") == 0:
                self.log("大会员经验兑换成功（经验+10）")
                result.ok += 1
            else:
                self.log_warn(f"大会员经验兑换失败：{j.get('message') or j.get('msg')}")

    def _watch_for_express(self, client):
        from .daily import DailyTask

        daily = DailyTask(self.opts)
        daily.tag = self.tag
        video = daily.pick_random_video(client)
        if video:
            daily.watch_video(client, video, TaskResult("express-watch"))

    def three_day_sign(self, client, result):
        j = client.get(
            THREE_DAYS_SIGN,
            params={"csrf": client.account.csrf},
            referer="https://big.bilibili.com/mobile/bigPoint/task",
        )
        data = j.get("data") or {}
        sign_info = data.get("three_day_sign") or {}
        if sign_info.get("signed"):
            self.log("大积分签到已完成，跳过")
            return
        params = {
            "mobi_app": "android",
            "csrf": client.account.csrf,
            "platform": "android",
        }
        body = {"device": "phone", "t": int(time.time() * 1000)}
        j = client.post(
            SIGN2,
            params=params,
            json_body=body,
            referer="https://big.bilibili.com/mobile/index",
        )
        if j.get("code") == 0:
            d = j.get("data") or {}
            self.log(
                f"大积分签到成功（经验+{d.get('score', '?')}，累计 {d.get('count', '?')}/{d.get('duration', '?')} 天）"
            )
            result.ok += 1
        else:
            self.log(f"大积分签到失败：{j.get('message') or j.get('msg')}")
            result.fail += 1

    def get_combine(self, client):
        j = client.get(
            TASK_COMBINE,
            params={"csrf": client.account.csrf, "buvid": client.account.get("buvid3", "")},
            referer="https://big.bilibili.com/mobile/bigPoint/task",
        )
        if j.get("code") != 0:
            raise RuntimeError(j.get("message") or j.get("msg"))
        return j.get("data") or {}

    def log_task_modules(self, combine):
        for module in (combine.get("task_info") or {}).get("modules") or []:
            items = module.get("common_task_item") or []
            states = {0: "未领取", 1: "已领取", 2: "进行中", 3: "已完成"}
            desc = "、".join(
                f"{it.get('title')}({states.get(it.get('state'), it.get('state'))})"
                for it in items
            )
            self.log(f"[大积分] {module.get('module_title')}: {desc}")

    def one_time_mission(self, client, combine, module_code, task_code, result):
        item = self._find_task(combine, module_code, task_code)
        if item is None:
            self.log(f"[大积分] 任务 {task_code} 不存在或已失效")
            return
        if item.get("state") == 3:
            self.log(f"[大积分] {item.get('title')} 已完成，跳过")
            return
        if item.get("state") == 0:
            self._receive_task(client, task_code)
        self._complete_v2(client, task_code)
        self.log(f"[大积分] {item.get('title')} 完成")
        result.ok += 1

    def daily_missions(self, client, combine, result):
        missions = [
            ("dress-view", "浏览装扮商城", self._complete_v2),
            ("vipmallview", "浏览会员购", self._complete_vip_mall),
            ("animatetab", "浏览追番频道", lambda c, t: self._deliver_view(c, "jp_channel")),
            ("filmtab", "浏览影视频道", lambda c, t: self._deliver_view(c, "tv_channel")),
            ("ogvwatchnew", "观看剧集", self._complete_v2),
        ]
        for task_code, title, complete_fn in missions:
            item = self._find_task(combine, "日常任务", task_code)
            if item is None:
                continue
            if item.get("state") == 3:
                self.log(f"[大积分] {title} 已完成，跳过")
                continue
            if item.get("state") == 0:
                self._receive_task(client, task_code)
            if task_code in ("animatetab", "filmtab"):
                self.log(f"[大积分] 开始浏览{title}，等待 10 秒模拟浏览...")
                time.sleep(10)
            ok = self.safe(complete_fn, client, task_code)
            if ok:
                self.log(f"[大积分] {title} 完成")
                result.ok += 1
            else:
                self.log_warn(f"[大积分] {title} 完成失败")

    # ------------------------------------------------------------- 子步骤
    def _find_task(self, combine, module_code, task_code):
        for module in (combine.get("task_info") or {}).get("modules") or []:
            if module.get("module_title") != module_code:
                continue
            for item in module.get("common_task_item") or []:
                if item.get("task_code") == task_code:
                    return item
        return None

    def _receive_task(self, client, task_code):
        j = client.post(
            TASK_RECEIVE_V2,
            data={"task_code": task_code},
            referer="https://big.bilibili.com/mobile/bigPoint/task",
        )
        if j.get("code") != 0:
            self.log(f"[大积分] 领取任务 {task_code} 失败：{j.get('message') or j.get('msg')}")

    def _complete_v2(self, client, task_code):
        j = client.post(
            TASK_COMPLETE_V2,
            data={"task_code": task_code},
            referer="https://big.bilibili.com/mobile/bigPoint/task",
        )
        return j.get("code") == 0

    def _complete_vip_mall(self, client, _task_code):
        j = client.post(
            VIP_MALL_DISPATCH,
            json_body={"csrf": client.account.csrf, "eventId": "hevent_oy4b7h3epeb"},
            referer="https://show.bilibili.com/",
            origin="https://show.bilibili.com",
        )
        return j.get("code") == 0

    def _deliver_view(self, client, position):
        data = {
            "position": position,
            "c_locale": "zh_CN",
            "channel": "bili",
            "s_locale": "zh_CN",
            "build": "8451100",
            "disable_rcmd": 0,
            "mobi_app": "android",
            "platform": "android",
            "statistics": '{"appId":1,"platform":3,"version":"8.45.1","abtest":""}',
            "t": int(time.time() * 1000),
        }
        j = client.post(
            TASK_DELIVER,
            data=data,
            referer="https://big.bilibili.com/mobile/bigPoint/task",
        )
        return j.get("code") == 0
