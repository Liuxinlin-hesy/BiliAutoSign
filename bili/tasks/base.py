# -*- coding: utf-8 -*-
"""任务基类与注册表。"""
from .. import logger
from ..client import BiliClient, BiliRequestError


class TaskResult:
    def __init__(self, name, ok=0, fail=0, notes=None):
        self.name = name
        self.ok = ok
        self.fail = fail
        self.notes = notes or []


class Task:
    """任务基类。

    子类实现 run(client) -> TaskResult。opts 为全局配置 dict。
    """

    name = ""
    title = ""

    def __init__(self, opts):
        self.opts = opts
        self.tag = ""

    def run(self, client: BiliClient) -> TaskResult:
        raise NotImplementedError

    def log_ok(self, msg):
        logger.ok(msg, self.tag)

    def log(self, msg):
        logger.info(msg, self.tag)

    def log_warn(self, msg):
        logger.warn(msg, self.tag)

    def log_err(self, msg):
        logger.error(msg, self.tag)

    def safe(self, fn, *a, **kw):
        """执行子步骤，异常吞掉并返回 None（单个子步骤失败不影响整体）。"""
        try:
            return fn(*a, **kw)
        except BiliRequestError as e:
            self.log_err(f"请求异常: {e}")
        except Exception as e:  # noqa: BLE001
            self.log_err(f"异常: {e}")
        return None

    def check_risk(self, client: BiliClient) -> bool:
        """返回 True 表示应跳过（风控受限）。"""
        if client.risk_limited:
            self.log_warn("账号已被风控受限标记，跳过写操作")
            return True
        return False


TASK_REGISTRY = {}


def register(cls):
    TASK_REGISTRY[cls.name] = cls
    return cls
