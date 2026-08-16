# 青龙面板部署指南

在 [青龙面板](https://github.com/whyour/qinglong)（2.x，docker 版 `whyour/qinglong:latest`）中
部署 BiliAutoSign。无需 config.json，所有配置通过青龙环境变量完成。

## 1. 安装依赖（青龙容器内）

青龙面板 → 依赖管理 → Python 依赖，添加：

```
requests
qrcode
colorama
```

或进入容器执行 `pip3 install requests qrcode colorama`。

## 2. 拉取代码

青龙面板 → 脚本管理（或容器内）：

```bash
cd /ql/scripts
git clone https://github.com/Liuxinlin-hesy/BiliAutoSign.git
```

## 3. 配置环境变量

青龙面板 → 环境变量，添加：

| 变量名 | 说明 | 示例 |
| --- | --- | --- |
| `Ray_BiliBiliCookies__0` | 账号 cookie（BiliBiliToolPro 兼容命名，从 0 开始递增） | `SESSDATA=...; bili_jct=...; DedeUserID=...` |
| `Ray_BiliBiliCookies__1` | 第二个账号，以此类推 | |
| `BILI_COOKIE` | 替代方案：单变量多账号，**一行一个**（值内换行） | |
| `QL_CLIENT_ID` / `QL_CLIENT_SECRET` | 青龙 OpenAPI 凭据（面板 → 系统设置 → OpenAPI），用于运行结束推送通知 | |
| `QL_BASE_URL` | 青龙面板地址，容器内默认 `http://127.0.0.1:5600`，一般无需设置 | |

### 可选配置（环境变量覆盖默认值）

| 变量名 | 对应配置项 | 默认 |
| --- | --- | --- |
| `BILI_TASKS` | 运行的任务（逗号分隔） | `daily,live,manga,vip` |
| `BILI_NUMBER_OF_COINS` | 每日投币数 | `5` |
| `BILI_PROTECTED_COINS` | 保留硬币数 | `0` |
| `BILI_SELECT_LIKE` | 投币同时点赞 | `false` |
| `BILI_SAVE_COINS_LV6` | LV6 跳过投币 | `false` |
| `BILI_SUPPORT_UP_IDS` | 优先 UP 主（逗号分隔） | 空 |
| `BILI_INTERVAL` | API 调用间隔上限（秒） | `3` |
| `BILI_RANDOM_SLEEP` | 运行前随机休眠最大分钟数（**建议 `10` 随机化运行时间**） | `0` |
| `BILI_TICKET` | 是否获取 bili_ticket | `true` |
| `BILI_LOTTERY` | 开启天选时刻 | `false` |
| `BILI_FANS_MEDAL` | 开启粉丝勋章 | `false` |
| `BILI_SILVER2COIN` | 银瓜子兑换 | `true` |
| `BILI_DEVICE_PLATFORM` | 漫画平台（android/ios） | `android` |
| `BILI_PROXY` | HTTP 代理 | 空 |
| `QL_NOTIFY_FAIL_ONLY` | 仅失败时推送通知 | `true` |

## 4. 创建定时任务

青龙面板 → 定时任务 → 新建：

- 名称：`BiliAutoSign`
- 命令：`task BiliAutoSign/qinglong/entry.py run`（或 `python3 /ql/scripts/BiliAutoSign/main.py run`）
- 定时规则：建议避开整点高峰，如 `10 9 * * *`（每天 9:10）
- 任务可见性：新建任务后默认隐藏，编辑任务勾选「运行日志」查看输出

## 5. 验证

先手动运行一次任务，日志中应看到各账号的签到结果；
配置了 `QL_CLIENT_ID/QL_CLIENT_SECRET` 时，运行结束（有失败项时）会通过青龙推送通知。

## 说明

- 青龙下账号来自环境变量，工具**不会**把补齐的 buvid3/bili_ticket 写回任何文件
  （青龙环境变量为只读，需定期手动刷新 cookie；bili_ticket 每次运行自动重新获取）。
- cookie 过期（`-101 账号未登录`）时任务会明确报错，请及时在面板更新环境变量。
