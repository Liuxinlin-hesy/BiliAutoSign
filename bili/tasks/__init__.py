# -*- coding: utf-8 -*-
from .base import Task, TaskResult, TASK_REGISTRY
from .daily import DailyTask
from .live import LiveTask
from .manga import MangaTask
from .vip import VipBigPointTask
from .lottery import LotteryTask
from .fansmedal import FansMedalTask

__all__ = [
    "Task", "TaskResult", "TASK_REGISTRY",
    "DailyTask", "LiveTask", "MangaTask", "VipBigPointTask",
    "LotteryTask", "FansMedalTask",
]


def build_tasks(names, opts):
    """根据名称列表构建任务实例（保持注册顺序）。"""
    tasks = []
    for name in names:
        cls = TASK_REGISTRY.get(name)
        if cls is None:
            raise ValueError(f"未知任务: {name}（可用: {', '.join(TASK_REGISTRY)}）")
        tasks.append(cls(opts))
    return tasks
