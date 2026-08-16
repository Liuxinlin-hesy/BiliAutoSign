# -*- coding: utf-8 -*-
"""直播任务：银瓜子兑换硬币（直播每日签到活动已下线，已移除）。

对应 BiliBiliToolPro：
- 银瓜子兑换硬币：GET /xlive/revenue/v1/wallet/getStatus + POST /xlive/revenue/v1/wallet/silver2coin
"""
from .. import logger
from .base import Task, TaskResult, register

WALLET_STATUS_URL = "https://api.live.bilibili.com/xlive/revenue/v1/wallet/getStatus"
SILVER2COIN_URL = "https://api.live.bilibili.com/xlive/revenue/v1/wallet/silver2coin"


@register
class LiveTask(Task):
    name = "live"
    title = "直播任务（银瓜子兑换硬币）"

    def run(self, client):
        self.tag = client.tag
        result = TaskResult(self.name)
        if client.risk_limited:
            self.log_warn("账号风控受限，跳过直播任务")
            return result

        self.silver2coin(client, result)
        return result

    def silver2coin(self, client, result):
        if not self.opts.get("is_silver2coin", True):
            self.log("已配置跳过银瓜子兑换")
            return
        j = client.get(
            WALLET_STATUS_URL,
            referer="https://link.bilibili.com/p/center/index",
        )
        if j.get("code") != 0:
            self.log(f"查询直播钱包失败：{j.get('message') or j.get('msg')}")
            return
        data = j.get("data") or {}
        silver = data.get("silver") or 0
        left = data.get("silver_2_coin_left") or 0
        self.log(f"银瓜子 {silver} | 今日剩余兑换次数 {left}")
        if left <= 0:
            self.log("今日兑换次数已用完")
            return
        if silver < 700:
            self.log("银瓜子不足 700，跳过兑换")
            return
        j = client.post(
            SILVER2COIN_URL,
            params={"csrf": client.account.csrf},
            data={},
            referer="https://link.bilibili.com/p/center/index",
        )
        if j.get("code") == 0:
            data = j.get("data") or {}
            self.log(f"银瓜子兑换成功：+{data.get('coin', '?')} 硬币，剩余银瓜子 {data.get('silver', '?')}")
            result.ok += 1
        else:
            self.log(f"银瓜子兑换失败：{j.get('message') or j.get('msg')}")
            result.fail += 1
