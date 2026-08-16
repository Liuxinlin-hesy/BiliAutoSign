# -*- coding: utf-8 -*-
"""BiliAutoSign CLI 入口。

用法：
  python main.py run                 # 运行默认任务（daily,live,manga,vip）
  python main.py run -t daily,live   # 只运行指定任务
  python main.py run -a 1,2          # 只运行第 1、2 个账号
  python main.py check               # 检测配置的 cookie 是否有效
  python main.py login               # 扫码登录，获取新 cookie
  python main.py init                # 生成配置文件
"""
import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bili import logger  # noqa: E402
from bili.__init__ import __version__  # noqa: E402
from bili.account import Account  # noqa: E402
from bili.client import BiliClient, BiliRequestError  # noqa: E402
from bili.config import (  # noqa: E402
    env_config_overrides,
    load_config,
    load_env_cookies,
    ql_env_config,
    save_config,
    update_cookie_in_config,
)
from bili.tasks import build_tasks, TASK_REGISTRY  # noqa: E402

ALL_TASKS = ["daily", "live", "manga", "vip", "lottery", "fansmedal"]


def get_accounts(cfg, cli_cookie=None, cli_accounts=None):
    """账号来源优先级：--cookie 参数 > 青龙环境变量 > config.json cookies。

    青龙环境变量：
    - BILI_COOKIE：多账号用换行分隔
    - Ray_BiliBiliCookies__0 / __1 / ...：BiliBiliToolPro 兼容
    返回 (accounts, from_env)。from_env=True 时表示账号来自环境变量（青龙）。
    """
    cookies = []
    from_env = False
    if cli_cookie:
        cookies.append(cli_cookie)
    else:
        env_cookies, env_found = load_env_cookies()
        if env_found:
            cookies = env_cookies
            from_env = True
        else:
            cookies += [c for c in (cfg.get("cookies") or []) if c]

    accounts = []
    for i, ck in enumerate(cookies):
        acct = Account(ck, name=f"#{i + 1}")
        missing = acct.validate()
        if missing:
            logger.warn(f"[账号 {i + 1}] 配置异常：{'；'.join(missing)}，跳过")
            continue
        accounts.append(acct)

    if cli_accounts:
        idxs = []
        for part in cli_accounts.split(","):
            part = part.strip()
            if part.isdigit():
                idxs.append(int(part) - 1)
        accounts = [a for i, a in enumerate(accounts) if i in idxs]
    return accounts, from_env


def select_tasks(cfg, cli_tasks):
    if cli_tasks:
        names = [t.strip() for t in cli_tasks.split(",") if t.strip()]
    else:
        names = [t for t in (cfg.get("tasks") or ["daily", "live", "manga", "vip"]) if t in ALL_TASKS]
        if cfg.get("enable_lottery") and "lottery" not in names:
            names.append("lottery")
        if cfg.get("enable_fans_medal") and "fansmedal" not in names:
            names.append("fansmedal")
    return names


def random_sleep(cfg):
    minutes = int(cfg.get("random_sleep_max_min", 0) or 0)
    if minutes > 0:
        m = random.randint(1, minutes)
        logger.info(f"随机休眠 {m} 分钟（避免固定时间点触发风控）")
        time.sleep(m * 60)


def run_tasks(cfg, names, accounts, config_path, persist=True):
    tasks = build_tasks(names, cfg)
    random_sleep(cfg)

    rows = []
    for acct in accounts:
        logger.section(f"账号 {acct.uid}（{acct.name or '配置账号'}）")
        client = BiliClient(acct, cfg)
        changed = False
        try:
            client.ensure_device()
            if persist:
                changed = update_cookie_in_config(cfg, acct, config_path)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"设备初始化失败：{e}")
        if changed:
            logger.info("已更新 cookie（buvid3/bili_ticket 等已持久化）")

        ok_count = fail_count = 0
        notes = []
        for task in tasks:
            try:
                res = task.run(client)
                ok_count += res.ok
                fail_count += res.fail
                for n in res.notes:
                    notes.append(n)
            except Exception as e:  # noqa: BLE001
                fail_count += 1
                logger.error(f"[{task.name}] 任务异常：{e}")
        rows.append((acct.uid, ok_count, fail_count, notes))

    logger.summary_table(rows)
    return rows


def merge_env_overrides(cfg):
    """合并青龙/BILI_* 环境变量（环境变量优先于 config.json）。"""
    return env_config_overrides(cfg)


def send_notify_if_needed(cfg, rows, names):
    """运行结束后按配置发送青龙通知。notify_fail_only=True 时仅失败才通知。"""
    if not (cfg.get("ql_client_id") and cfg.get("ql_client_secret")):
        return
    total_fail = sum(r[2] for r in rows)
    fail_only = str(cfg.get("notify_fail_only", "true")).lower() in ("1", "true", "yes")
    if fail_only and total_fail == 0:
        logger.info("任务全部成功，按配置（notify_fail_only）跳过通知")
        return
    title = "BiliAutoSign 运行完成" if total_fail == 0 else f"BiliAutoSign 运行异常（{total_fail} 项失败）"
    from bili.notify import build_summary, send_qinglong_notify

    send_qinglong_notify(cfg, title, build_summary(rows, names))


def cmd_run(args, cfg, config_path):
    names = select_tasks(cfg, getattr(args, "tasks", None))
    logger.info(f"目标任务：{', '.join(names)}（共 {len(names)} 个）")
    accounts, from_env = get_accounts(
        cfg,
        getattr(args, "cookie", None),
        getattr(args, "accounts", None),
    )
    if not accounts:
        logger.error("没有可用的账号：请检查 config.json 的 cookies 或配置环境变量（BILI_COOKIE / Ray_BiliBiliCookies__N）")
        sys.exit(1)
    logger.info(f"共 {len(accounts)} 个账号参与本次运行"
                + ("（来自青龙环境变量）" if from_env else ""))
    cfg = merge_env_overrides(cfg)
    rows = run_tasks(cfg, names, accounts, config_path, persist=not from_env)
    send_notify_if_needed(cfg, rows, names)


def cmd_check(args, cfg, _config_path=None):
    accounts, from_env = get_accounts(
        cfg,
        getattr(args, "cookie", None),
        getattr(args, "accounts", None),
    )
    if not accounts:
        logger.error("没有可用的账号")
        sys.exit(1)
    ok_all = True
    for acct in accounts:
        client = BiliClient(acct, cfg)
        try:
            info = client.user_info()
            level = (info.get("level_info") or {}).get("current_level")
            vip = {0: "无", 1: "月度", 2: "年度"}.get(info.get("vipType"), "?")
            logger.ok(
                f"{acct.uid}：{info.get('uname')} | 等级 {level} | 硬币 {info.get('money')} | 大会员 {vip}"
            )
        except BiliRequestError as e:
            ok_all = False
            logger.error(f"{acct.uid}：登录校验失败（{e}）")
    if not ok_all:
        sys.exit(1)


def cmd_login(args, cfg, config_path):
    import requests

    from bili.client import DEFAULT_UA

    s = requests.Session()
    s.headers.update({"User-Agent": args.ua or DEFAULT_UA,
                      "Accept": "application/json, text/plain, */*"})
    j = s.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
              timeout=20).json()
    if j.get("code") != 0:
        logger.error(f"获取二维码失败：{j.get('message')}")
        sys.exit(1)
    url = j["data"]["url"]
    key = j["data"]["qrcode_key"]
    logger.info("请使用 B 站手机客户端扫描下方二维码（终端不支持时访问：")
    logger.info("https://tool.lu/qrcode/basic.html?text=" + requests.utils.quote(url))
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception:  # noqa: BLE001
        logger.warn("（无法在终端绘制二维码）")
    logger.info("等待扫码...（120 秒超时）")

    deadline = time.time() + 120
    cookie_parts = {}
    while time.time() < deadline:
        time.sleep(2)
        r = s.get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
            params={"qrcode_key": key, "source": "main_mini"},
            timeout=20,
        )
        j = r.json()
        code = (j.get("data") or {}).get("code", j.get("code"))
        if code == 0:
            for v in r.headers.get_list("Set-Cookie") or []:
                for part in v.split(";"):
                    part = part.strip()
                    if "=" in part and not part.lower().startswith(("path=", "expires=",
                                                                      "domain=", "max-age=",
                                                                      "httponly", "secure",
                                                                      "samesite")):
                        k, val = part.split("=", 1)
                        cookie_parts[k.strip()] = val.strip()
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_parts.items())
            logger.ok("扫码成功！")
            logger.info(f"Cookie：\n{cookie_str}")
            if args.save:
                cookies = cfg.get("cookies") or []
                cookies.append(cookie_str)
                cfg["cookies"] = cookies
                save_config(cfg, config_path)
                logger.ok(f"已保存到 {config_path}")
            return
        if code == 86038:
            logger.error("二维码已失效，请重新运行 login")
            sys.exit(1)
        msg = {86101: "等待扫码...", 86090: "已扫码，请在手机上确认"}.get(code, f"状态 {code}")
        logger.info(msg)
    logger.error("扫码登录超时")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="BiliAutoSign",
        description=f"B 站每日签到工具 v{__version__}（参考 BiliBiliToolPro / PiliPlusX）",
    )
    parser.add_argument("--config", default=None, help="配置文件路径（默认 ./config.json）")
    # 顶层也提供 run 的参数（无子命令时直接运行默认任务）
    parser.add_argument("-t", "--tasks", default=None, help=f"任务列表，逗号分隔：{','.join(ALL_TASKS)}")
    parser.add_argument("-a", "--accounts", default=None, help="账号序号，逗号分隔（从 1 开始）")
    parser.add_argument("-c", "--cookie", default=None, help="临时指定单个 cookie")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="运行签到任务（默认命令）")
    p_run.add_argument("-t", "--tasks", default=None, help=f"任务列表，逗号分隔：{','.join(ALL_TASKS)}")
    p_run.add_argument("-a", "--accounts", default=None, help="账号序号，逗号分隔（从 1 开始）")
    p_run.add_argument("-c", "--cookie", default=None, help="临时指定单个 cookie")
    p_run.set_defaults(fn=cmd_run)

    p_check = sub.add_parser("check", help="检测 cookie 有效性")
    p_check.add_argument("-a", "--accounts", default=None, help="账号序号")
    p_check.add_argument("-c", "--cookie", default=None, help="临时指定单个 cookie")
    p_check.set_defaults(fn=cmd_check)

    p_login = sub.add_parser("login", help="扫码登录获取 cookie")
    p_login.add_argument("--save", action="store_true", help="登录成功后保存到配置文件")
    p_login.add_argument("--ua", default=None, help="登录请求使用的 User-Agent")
    p_login.set_defaults(fn=cmd_login)

    p_init = sub.add_parser("init", help="生成配置文件")
    p_init.set_defaults(fn=lambda a, cfg, path: logger.ok(f"配置文件：{path}"))

    p_ver = sub.add_parser("version", help="显示版本")
    p_ver.set_defaults(fn=lambda a, cfg, path: print(f"BiliAutoSign v{__version__}"))

    args = parser.parse_args()
    config_path = args.config
    cfg = load_config(config_path)
    if args.command in (None, "run"):
        args.fn = cmd_run
        cmd_run(args, cfg, config_path)
    else:
        args.fn(args, cfg, config_path)


if __name__ == "__main__":
    main()
