# BiliAutoSign

基于 [BiliBiliToolPro](https://github.com/RayWangQvQ/BiliBiliToolPro) 功能清单，参考
[PiliPlusX](https://github.com/cnctem/PiliPlusX) 与
[bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) 的
风控/签名实现，用 Python 编写的 B 站每日签到命令行工具。全程命令行操作，无 WebUI/GUI。

## 功能（对齐 BiliBiliToolPro 绝大部分任务）

| 任务 | 说明 | 接口 |
| --- | --- | --- |
| `daily` 每日任务 | 登录检查、每日任务状态、观看视频（心跳上报）、分享视频、投币（默认 5 枚，可配置）、大会员每月福利领取（B币券/权益） | `/x/web-interface/nav`、`/x/member/web/exp/reward`、`/x/click-interface/web/heartbeat`、`/x/web-interface/share/add`、`/x/web-interface/coin/add`、`/x/vip/privilege/receive` |
| `live` 直播任务 | 银瓜子兑换硬币（直播每日签到活动已下线，已移除） | `/xlive/revenue/v1/wallet/getStatus`、`silver2coin` |
| `manga` 漫画任务 | 漫画每日签到、自定义漫画阅读、大会员漫读劵 | `/twirp/activity.v1.Activity/ClockIn`、`AddHistory`、`GetVipReward` |
| `vip` 大会员任务 | 大会员大积分：经验加速包、三日签到、福利/体验任务、日常任务（浏览装扮商城/会员购/追番/影视、观看剧集） | `/x/vip/privilege/my`、`three_days_sign`、`/pgc/activity/score/task/*` |
| `lottery` 天选时刻（可选） | 扫描直播分区，自动参与免费天选抽奖 | `/xlive/lottery-interface/v1/Anchor/*` |
| `fansmedal` 粉丝勋章（可选） | 有粉丝牌的直播间点赞 + 直播心跳 | `MedalWall`、`likeReportV3`、`x25Kn/E/X` |
| `login` 扫码登录 | 终端二维码登录（TV/AAP 端点扫码，参考 PiliPlusX：独立登录身份 + APP 签名），可保存新 cookie | `/x/passport-tv-login/qrcode/auth_code`、`poll` |

任务默认按 `config.json` 中 `tasks` 配置运行（默认 `daily,live,manga,vip`）；
`lottery`/`fansmedal` 默认关闭，通过配置 `enable_lottery` / `enable_fans_medal` 开启。

## 风控策略（参考 PiliPlusX / bilibili-API-collect 优化）

1. **设备身份**：首次运行时通过 `/x/frontend/finger/spi` 获取 `buvid3/buvid4`，
   通过 `/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket`（hmac_sha256 签名）获取
   `bili_ticket`（有效期 3 天，可显著降低风控概率），并持久化回配置文件，保证设备身份稳定。
2. **WBI 签名**：对需要签名的接口（关注列表、UP 主视频列表等）自动携带 `w_rid/wts`，
   签名参数中包含 Web 端风控指纹 `dm_img_list/dm_img_str/dm_cover_img_str/dm_img_inter`
   （PiliPlusX 同款），避免 -352/-412 风控。
3. **请求节奏**：每次 API 调用前随机休眠 `[interval/2, interval]` 秒（默认 3 秒，
   与 BiliBiliToolPro 默认一致），避免短时高频请求；网络错误/5xx 自动重试。
4. **风控熔断**：遇到 -412/-352 标记账号为风控受限，跳过后续写操作；
   投币/分享连续被 -403（账号异常）时先 30 秒冷却再试，仍失败则中止，
   避免无效高频写操作加重风控。
5. **浏览器请求头**：按接口域名自动设置 Referer/Origin（与 BiliBiliToolPro 的
   Header 属性一致），UA 默认为 Chrome 122。

## 安装

```bash
pip install -r requirements.txt
```

仅依赖 `requests`（HTTP）、`qrcode`（登录二维码）、`colorama`（Windows 颜色输出）。

## 使用

```bash
# 1. 生成配置文件
python main.py init
# 2. 编辑 config.json，填入 cookies（可多个，每行一个）
# 3. 检测 cookie 有效性
python main.py check
# 4. 运行全部任务（所有账号）
python main.py run
# 指定任务 / 指定账号
python main.py run -t daily,live -a 2
# 临时指定 cookie 运行（不写入配置）
python main.py run -c "SESSDATA=...; bili_jct=..."
# 扫码登录获取 cookie（--save 保存到配置）
python main.py login --save
```

### 配置项（config.json）

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `cookies` | `[]` | 账号 cookie 字符串数组 |
| `tasks` | `["daily","live","manga","vip"]` | 运行的任务列表 |
| `number_of_coins` | `5` | 每日投币数（0-5） |
| `number_of_protected_coins` | `0` | 保留的硬币数，低于该值不投币 |
| `select_like` | `false` | 投币时是否同时点赞 |
| `save_coins_when_lv6` | `false` | LV6 后跳过投币 |
| `support_up_ids` | `[]` | 优先投币/观看的 UP 主 id 列表 |
| `is_silver2coin` | `true` | 是否执行银瓜子兑换硬币 |
| `device_platform` | `android` | 漫画接口的客户端平台 |
| `custom_comic_id`/`custom_ep_id` | `0` | 漫画阅读任务（0 关闭） |
| `interval_seconds_between_request_api` | `3` | 两次 API 调用间的随机间隔上限（秒） |
| `random_sleep_max_min` | `0` | 运行前随机休眠最大分钟数 |
| `enable_bili_ticket` | `true` | 是否获取 bili_ticket |
| `enable_lottery` / `enable_fans_medal` | `false` | 开启可选任务 |
| `persist_cookies` | `true` | 将补齐的 buvid3/bili_ticket 写回配置文件 |
| `user_agent` / `web_proxy` | 空 | 自定义 UA / 代理 |
| `ql_base_url` / `ql_client_id` / `ql_client_secret` | 空 | 青龙 OpenAPI 通知凭据 |
| `notify_fail_only` | `true` | 青龙通知：仅失败时推送 |

## 青龙面板部署

支持直接在[青龙面板](https://github.com/whyour/qinglong)（2.x）中运行，无需 config.json：

```bash
cd /ql/scripts
git clone https://github.com/Liuxinlin-hesy/BiliAutoSign.git
# 依赖：面板 → 依赖管理 → Python 依赖安装 requests、qrcode、colorama
```

1. **环境变量**（面板 → 环境变量）：
   - 账号：`Ray_BiliBiliCookies__0`、`Ray_BiliBiliCookies__1`...（BiliBiliToolPro 兼容命名），
     或 `BILI_COOKIE`（多账号换行分隔）
   - 通知（可选）：`QL_CLIENT_ID` / `QL_CLIENT_SECRET`（面板 → 系统设置 → OpenAPI）
   - 任务参数：所有配置项均可用 `BILI_*` 环境变量覆盖，如 `BILI_NUMBER_OF_COINS=5`、
     `BILI_RANDOM_SLEEP=10`、`BILI_TASKS=daily,live,manga,vip`
2. **定时任务**：新建任务，命令
   `task BiliAutoSign/qinglong/entry.py run`（或 `python3 /ql/scripts/BiliAutoSign/main.py run`），
   定时规则如 `10 9 * * *`（每天 9:10，建议避开整点）
3. 青龙下 cookie 来自环境变量，工具不会写回文件；运行结束（有失败项时）推送青龙通知。

详见 [qinglong/README.md](qinglong/README.md)。

## 目录结构

```
main.py                 CLI 入口
config.json             配置文件（自动生成）
qinglong/
  entry.py              青龙面板入口脚本
  README.md             青龙部署指南
bili/
  risk.py               WBI 签名、buvid3/4、bili_ticket、指纹参数
  login.py              TV/APP 端点扫码登录（独立身份 + APP 签名）
  client.py             风控 HTTP 客户端（间隔/重试/熔断/签名）
  account.py            cookie 解析与校验
  notify.py             青龙 OpenAPI 通知
  tasks/
    daily.py            每日任务（登录/观看/分享/投币/福利）
    live.py             银瓜子兑换硬币
    manga.py            漫画签到/阅读/漫读劵
    vip.py              大会员福利/大积分
    lottery.py          天选时刻（可选）
    fansmedal.py        粉丝勋章（可选）
```

## 免责声明

本项目仅供学习交流，请勿滥用。账号异常、风控等由使用者的操作方式与账号状态决定，
请合理使用、自行承担风险。
