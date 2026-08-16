# -*- coding: utf-8 -*-
"""每日任务：登录 + 每日任务状态 + 观看/分享视频 + 投币 + 大会员福利领取。

对应 BiliBiliToolPro 的 DailyTaskAppService：
- 登录（/x/web-interface/nav）
- 每日任务状态（/x/member/web/exp/reward）
- 观看视频（/x/click-interface/web/heartbeat，打开一次 + 播放一次）
- 分享视频（/x/web-interface/share/add）
- 投币（/x/web-interface/coin/add，默认 5 枚，受余额/保留币数约束）
- 领取大会员福利（/x/vip/privilege/receive，type=1 B币券 / type=2 大会员权益）
"""
import random
import time

from .. import logger
from ..client import BiliRequestError
from .base import Task, TaskResult, register

HEARTBEAT_URL = "https://api.bilibili.com/x/click-interface/web/heartbeat"
SHARE_URL = "https://api.bilibili.com/x/web-interface/share/add"
COIN_ADD_URL = "https://api.bilibili.com/x/web-interface/coin/add"
ARCHIVE_COINS_URL = "https://api.bilibili.com/x/web-interface/archive/coins"
VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
RANKING_URL = "https://api.bilibili.com/x/web-interface/ranking/v2"
ARC_SEARCH_URL = "https://api.bilibili.com/x/space/wbi/arc/search"
FOLLOWINGS_URL = "https://api.bilibili.com/x/relation/followings"
TODAY_EXP_URL = "https://api.bilibili.com/x/web-interface/coin/today/exp"
GET_COIN_URL = "https://account.bilibili.com/site/getCoin"
EXP_REWARD_URL = "https://api.bilibili.com/x/member/web/exp/reward"
VIP_RECEIVE_URL = "https://api.bilibili.com/x/vip/privilege/receive"

# 风控指纹参数（与 Web 端一致，heartbeat 请求体同样携带）
_DM_PARAMS = {
    "dm_img_list": "[]",
    "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
    "dm_cover_img_str": (
        "QU5HTEUgKE5WSURJQSwgTlZJRElBIEdlRm9yY2UgR1RYIDEwNjAgNkdCIERpcmVjdDNEMTEg"
        "dnNfNV8wIHBzXzVfMCwgRDNEMTEp"
    ),
    "dm_img_inter": '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}',
}


@register
class DailyTask(Task):
    name = "daily"
    title = "每日任务（登录/观看/分享/投币/福利）"

    def run(self, client):
        self.tag = client.tag
        result = TaskResult(self.name)
        if client.risk_limited:
            self.log_warn("账号风控受限，跳过每日任务")
            return result

        user_info = self.login(client, result)
        if not user_info:
            return result

        daily_status = self.safe(self.get_daily_status, client)
        if daily_status is None:
            daily_status = {}

        self.watch_and_share(client, user_info, daily_status, result)
        if client.risk_limited:
            return result
        self.add_coins(client, user_info, result)
        self.receive_vip_privilege(client, user_info, result)
        return result

    # ------------------------------------------------------------- 登录
    def login(self, client, result):
        try:
            user_info = client.user_info()
        except BiliRequestError as e:
            self.log_err(f"登录失败: {e}")
            result.fail += 1
            return None
        level = (user_info.get("level_info") or {}).get("current_level")
        vip = user_info.get("vip_status") or 0
        vip_type = user_info.get("vipType") or 0
        vip_desc = {0: "无大会员", 1: "月度大会员", 2: "年度大会员"}.get(vip_type, "大会员")
        self.log(
            f"登录成功：{user_info.get('uname', '?')}（uid {user_info.get('mid')}）"
            f" | 等级 {level} | 硬币 {user_info.get('money', '?')} | {vip_desc}"
        )
        result.ok += 1
        return user_info

    def get_daily_status(self, client):
        j = client.get(EXP_REWARD_URL)
        data = j.get("data") or {}
        coins = data.get("coins") or 0
        self.log(
            "每日任务状态：登录{} 观看{} 分享{} 投币{}（今日投币经验 {}）".format(
                "✓" if data.get("login") else "✗",
                "✓" if data.get("watch") else "✗",
                "✓" if data.get("share") else "✗",
                "✓" if coins > 0 else "✗",
                coins,
            )
        )
        return data

    # ------------------------------------------------------------- 观看/分享
    def watch_and_share(self, client, user_info, daily_status, result):
        need_watch = not daily_status.get("watch") and self.opts.get("is_watch_video", True)
        need_share = not daily_status.get("share") and self.opts.get("is_share_video", True)
        if not need_watch and not need_share:
            self.log("观看/分享任务今日已完成，跳过")
            return

        video = self.safe(self.pick_random_video, client)
        if not video:
            self.log_warn("未获取到可用视频，跳过观看/分享")
            result.fail += 1
            return
        self.log(f"随机视频：{video.get('title', '?')}（{video.get('bvid', '')}）")

        watched = False
        if need_watch:
            watched = self.watch_video(client, video, result)
        if need_share:
            if not watched:
                self.open_video(client, video)
            self.share_video(client, video, result)

    def watch_video(self, client, video, result):
        if not self.open_video(client, video):
            result.fail += 1
            return False
        duration = video.get("duration") or 15
        played = random.randint(1, min(duration, 15))
        ok = self.heartbeat(client, video, played)
        if ok:
            self.log(f"视频播放成功，已观看到第 {played} 秒（经验+5）")
            result.ok += 1
            return True
        self.log_err("视频播放上报失败")
        result.fail += 1
        return False

    def open_video(self, client, video):
        return self.heartbeat(client, video, 0)

    def heartbeat(self, client, video, played_time):
        data = {
            "aid": video["aid"],
            "bvid": video.get("bvid", ""),
            "cid": video.get("cid", 0),
            "mid": client.account.uid,
            "csrf": client.account.csrf,
            "played_time": played_time,
            "realtime": played_time,
            "real_played_time": played_time,
            "start_ts": int(time.time()) - played_time,
            "type": 3,
            "dt": 2,
            "play_type": 3,
        }
        data.update(_DM_PARAMS)
        j = client.post(
            HEARTBEAT_URL,
            params={"aid": video["aid"], "played_time": played_time},
            data=data,
            referer=f"https://www.bilibili.com/video/{video.get('bvid', '')}",
        )
        return j.get("code") == 0

    def share_video(self, client, video, result):
        data = {
            "aid": video["aid"],
            "csrf": client.account.csrf,
            "eab_x": "1",
            "ramval": str(random.randint(3, 19)),
            "source": "web_normal",
            "ga": "1",
        }
        j = client.post(
            SHARE_URL, data=data,
            referer=f"https://www.bilibili.com/video/{video.get('bvid', '')}",
        )
        if j.get("code") == 0:
            self.log("视频分享成功（经验+5）")
            result.ok += 1
            return
        if j.get("code") == -403:
            # 风控优化：-403 先冷却一次再重试（新号/新设备首次写操作常被短暂拦截）
            self.log_warn("分享被 -403 拒绝，等待 20 秒冷却后重试一次...")
            time.sleep(20)
            j = client.post(
                SHARE_URL, data=data,
                referer=f"https://www.bilibili.com/video/{video.get('bvid', '')}",
            )
            if j.get("code") == 0:
                self.log("视频分享成功（经验+5，重试后）")
                result.ok += 1
                return
            self.log_warn("分享仍被 -403 拒绝（账号疑似处于风控观察期，明日自动再试）")
            result.fail += 1
            return
        self.log_err(f"视频分享失败：{j.get('message') or j.get('msg')}")
        result.fail += 1

    # ------------------------------------------------------------- 投币
    def add_coins(self, client, user_info, result):
        opts = self.opts
        target = int(opts.get("number_of_coins", 5))
        if target <= 0:
            self.log("已配置跳过投币任务")
            return
        if opts.get("save_coins_when_lv6") and (user_info.get("level_info") or {}).get(
            "current_level", 0
        ) >= 6:
            self.log("LV6 大佬，已配置白嫖，跳过投币")
            return

        j = client.get(TODAY_EXP_URL)
        donated = (j.get("data") or 0) // 10 if isinstance(j.get("data"), int) else 0
        need = target - donated
        if need <= 0:
            self.log("今日投币任务已完成，无需再投")
            return

        j = client.get(GET_COIN_URL)
        balance = (j.get("data") or {}).get("money") or 0
        protected = int(opts.get("number_of_protected_coins", 0))
        self.log(f"投币目标 {target} 枚 | 今日已投 {donated} 枚 | 硬币余额 {balance}")
        if balance <= protected:
            self.log("硬币余额达到或低于保留值，今日不执行投币任务")
            return
        if balance < need:
            need = int(balance)
        if balance - need <= protected and balance - protected < need:
            need = int(balance - protected)

        success = 0
        tried = set()
        consecutive_403 = 0
        cooled = False  # 已执行过一次 -403 冷却
        for _ in range(10):
            if success >= need:
                break
            video = self.safe(self.pick_coinable_video, client, tried)
            if not video:
                break
            tried.add(video["aid"])
            outcome = self.do_add_coin(client, video, result)
            if outcome == "ok":
                success += 1
                consecutive_403 = 0
            elif outcome == "risk403":
                consecutive_403 += 1
                # 风控优化：连续 -403 说明账号可能处于观察期，先冷却再试，
                # 仍失败则中止，避免无效高频写操作加重风控
                if consecutive_403 >= 3 and not cooled:
                    cooled = True
                    self.log_warn("连续多次操作被 -403 拒绝，等待 30 秒冷却后重试...")
                    time.sleep(30)
                elif consecutive_403 >= 6:
                    self.log_warn("账号写操作持续被 -403 拒绝（疑似风控观察期），停止投币尝试")
                    break
            else:
                consecutive_403 = 0
        if success >= need:
            self.log(f"视频投币任务完成（{success} 枚）")
        elif success > 0:
            self.log_warn(f"投币尝试结束，成功 {success} 枚")

    def pick_coinable_video(self, client, tried):
        """依次从 配置UP → 关注列表 → 排行榜 找未投满的视频。"""
        # 配置的 UP 主
        ups = self.opts.get("support_up_ids") or []
        for _ in range(len(ups) or 1):
            up = random.choice(ups) if ups else None
            video = self.safe(self.video_from_up, client, up) if up else None
            if video and video["aid"] not in tried and self.safe(self.is_coinable, client, video):
                return video
        # 关注列表
        following = self.safe(self.get_followings, client)
        if following:
            random.shuffle(following)
            for up in following[:5]:
                video = self.safe(self.video_from_up, client, up)
                if video and video["aid"] not in tried and self.safe(self.is_coinable, client, video):
                    return video
        # 排行榜
        for _ in range(5):
            video = self.safe(self.video_from_ranking, client)
            if video and video["aid"] not in tried and self.safe(self.is_coinable, client, video):
                return video
        return None

    def is_coinable(self, client, video):
        j = client.get(ARCHIVE_COINS_URL, params={"aid": video["aid"], "jsonp": "jsonp"})
        multiply = (j.get("data") or {}).get("multiply") or 0
        if multiply >= 2:
            return False
        view = self.safe(lambda: client.get(VIEW_URL, params={"aid": video["aid"]}))
        if view:
            copyright_ = (view.get("data") or {}).get("copyright")
            limit = 2 if copyright_ == 1 else 1
            if multiply >= limit:
                return False
        return True

    def do_add_coin(self, client, video, result):
        data = {
            "aid": video["aid"],
            "multiply": 1,
            "select_like": 1 if self.opts.get("select_like") else 0,
            "cross_domain": "true",
            "csrf": client.account.csrf,
            "eab_x": "2",
            "ramval": "3",
            "source": "web_normal",
            "ga": "1",
        }
        referer = (
            f"https://www.bilibili.com/video/{video.get('bvid', '')}/"
            "?spm_id_from=333.1007.tianma.1-1-1.click"
        )
        j = client.post(COIN_ADD_URL, data=data, referer=referer)
        if j.get("code") == 0:
            self.log(f"投币成功（经验+10）：{video.get('title', '?')}")
            result.ok += 1
            return "ok"
        if j.get("code") == -403:
            self.log_warn(f"投币被拒绝（-403 账号异常）：{video.get('title', '?')}")
            result.fail += 1
            return "risk403"
        if j.get("code") in (34005, 34004):
            self.log_warn(f"投币失败（{j.get('message')}），跳过该视频")
            return "skip"
        self.log_err(f"投币失败：{j.get('message') or j.get('msg')}")
        result.fail += 1
        return "err"

    # ------------------------------------------------------------- 大会员福利
    def receive_vip_privilege(self, client, user_info, result):
        if not (user_info.get("vip_status") and user_info.get("vipType") == 2):
            self.log("非年度大会员，跳过每月福利领取（B币券/大会员权益）")
            return
        for type_, name in ((1, "年度大会员 B币券"), (2, "大会员福利/权益")):
            j = client.post(
                VIP_RECEIVE_URL,
                params={"type": type_, "csrf": client.account.csrf},
                referer="https://account.bilibili.com/account/home",
                origin="https://account.bilibili.com",
            )
            if j.get("code") == 0:
                self.log(f"领取{name}成功")
                result.ok += 1
            else:
                self.log(f"领取{name}：{j.get('message') or j.get('msg')}")

    # ------------------------------------------------------------- 视频选取
    def get_followings(self, client):
        j = client.get(
            FOLLOWINGS_URL,
            params={
                "vmid": client.account.uid,
                "pn": 1,
                "ps": 50,
                "order": "desc",
                "order_type": "attention",
                "jsonp": "jsonp",
            },
            wbi=True,
        )
        data = j.get("data") or {}
        if j.get("code") != 0:
            raise BiliRequestError(f"获取关注列表失败: {j.get('message')}")
        return [item.get("mid") for item in (data.get("list") or []) if item.get("mid")]

    def video_from_up(self, client, up_id):
        j = client.get(
            ARC_SEARCH_URL,
            params={
                "mid": up_id,
                "ps": 30,
                "pn": 1,
                "tid": 0,
                "keyword": "",
                "order": "pubdate",
                "platform": "web",
                "web_location": 1550101,
                "order_avoided": "true",
            },
            wbi=True,
            referer=f"https://space.bilibili.com/{up_id}",
            origin="https://space.bilibili.com",
        )
        data = j.get("data") or {}
        vlist = ((data.get("list") or {}).get("vlist")) or []
        if not vlist:
            return None
        item = random.choice(vlist)
        return {
            "aid": item.get("aid"),
            "bvid": item.get("bvid", ""),
            "cid": item.get("cid", 0),
            "title": item.get("title", ""),
            "duration": item.get("length") or item.get("duration"),
        }

    def video_from_ranking(self, client):
        j = client.get(RANKING_URL, params={"rid": 0, "type": "all"})
        data = j.get("data") or {}
        lst = data.get("list") or []
        if not lst:
            return None
        item = random.choice(lst)
        return {
            "aid": item.get("aid"),
            "bvid": item.get("bvid", ""),
            "cid": item.get("cid", 0),
            "title": item.get("title", ""),
            "duration": item.get("duration"),
        }

    def pick_random_video(self, client):
        """观看/分享用：配置UP → 关注 → 排行榜。"""
        ups = self.opts.get("support_up_ids") or []
        if ups:
            video = self.safe(self.video_from_up, client, random.choice(ups))
            if video:
                return video
        following = self.safe(self.get_followings, client)
        if following:
            random.shuffle(following)
            for up in following[:5]:
                video = self.safe(self.video_from_up, client, up)
                if video:
                    return video
        return self.video_from_ranking(client)
