# AgentPlan

> 一个帮你**决定**、而不只是帮你**记住**的个人任务分诊 agent。

![status](https://img.shields.io/badge/status-building-orange) ![python](https://img.shields.io/badge/python-3.11+-blue) ![license](https://img.shields.io/badge/license-MIT-lightgrey)

信息太多、看到 A 又惦记 B、来回穿插，最后哪件都做不好——这个项目把"现在到底该做什么"从脑子里搬出来。你随手发一句话，它整理成任务、判断轻重缓急、到点提醒你，做完归档、没做完自动回流。

## 核心机制

打开"AI 问答"，随便聊你要做的事——AI 不会你一说"我要xxx"就立刻建一条任务，而是先追问清楚重要紧急程度、尤其是**时间**（这个必须问清楚，不会瞎猜），目标型的事还会给一个具体可执行的计划建议，聊明白了才真正创建/修改/删除任务。"计划列表"按 学习/工作/运动/食物/其他 分板块展示所有任务，可以直接编辑或删除。到点提醒推送到微信。

## 功能（v2）

- **AI 问答**：对话式创建/修改/删除任务，时间不清楚会主动追问，目标型任务给具体计划建议（不是一句话进、任务立刻出）
- **计划列表**：先看到分类色块（学习/工作/运动/食物/其他 + 一个"+"自定义），点进某个分类才看到里面的任务卡片，每个字段都能直接编辑，支持删除；点"+"可以自己命名新增分类
- 定时提醒，推送到微信
- 手动新建任务的入口依然保留（不想聊天时快速记一条）

## 架构

- **后端**：Python + SQLite，一个常驻调度器负责到点触发
- **智能层**：通义千问（Qwen，走阿里云百炼/DashScope），带 tool calling——AI 问答里创建/修改/删除任务都是它主动调用 `create_task`/`update_task`/`delete_task`/`list_open_tasks` 这几个工具完成的，不是一次性把整段话解析成 JSON
- **网页两视图，共用一个后端**：AI 问答（聊天） + 计划列表（按分类分板块，可编辑可删除）

提醒通道做成可插拔接口：面向国内使用，走 **Server酱 / PushPlus 转发到微信**（服务号模板消息）或企业微信机器人，不依赖 Telegram；网页本身负责查看和操作，不承担推送职责。

## 数据模型（核心表）

| 字段 | 说明 |
|---|---|
| title / notes | 主题 / 备注（链接、生成的计划）|
| category | 学习 / 工作 / 运动 / 食物 / 其他 |
| type | 单件事 `single`·目标型 `goal` |
| importance · urgency | 各 high·med·low |
| action | now / schedule / routine / drop |
| status | todo / doing / done / missed / routine / dropped |
| remind_at · snooze_until | 提醒时间 / 贪睡到点 |

## 本地运行

首次设置（只需一次）：

```
git clone https://github.com/bellading/Agent-Plan.git
cd Agent-Plan
git checkout claude/great-turing-mjkh2v
pip install -r requirements.txt
```

日常打开，双击对应脚本即可（网页 + 调度器一起启动，并自动打开浏览器）：

- macOS：双击 `start_mac.command`（首次双击如果提示"无法打开"，右键选"打开"确认一次即可）
- Windows：双击 `start_windows.bat`

不想用脚本、想自己在终端里跑也可以：

```
python3 app.py          # 网页表格页：http://127.0.0.1:5000
python3 scheduler.py    # 提醒调度器，另开一个终端常驻运行
```

网页只负责查看和编辑，不推送提醒；调度器要一直运行，到点才会真的推消息，所以长期用需要把它放到一台常开的机器上（自己电脑合盖/关机时不会提醒）。

### 配置提醒推送（Server酱）

1. 打开 https://sct.ftqq.com/ ，用微信扫码绑定，拿到一个 `SCT...` 开头的 SendKey
2. 二选一保存：
   - `export SERVERCHAN_SENDKEY=SCT...`（每次开终端要重新设置）
   - 或存到 `.secrets/serverchan_sendkey.txt`（已加入 .gitignore，不会被提交，重启后依然有效）
3. 不配置时调度器只会在终端打印"本该发送"的内容，不会报错，方便先跑通逻辑再接真实推送

### 配置 AI 问答（通义千问）

"AI 问答"视图需要一个 API Key 才能对话：

1. 打开 https://bailian.console.aliyun.com/ ，开通百炼/DashScope，拿到一个 `sk-...` 开头的 API Key
2. 二选一保存：
   - `export DASHSCOPE_API_KEY=sk-...`
   - 或存到 `.secrets/qwen_api_key.txt`（已加入 .gitignore）
3. 没配置时聊天会返回报错提示，不影响"计划列表"里手动新建/编辑/删除任务

## Roadmap

- [x] 数据模型
- [x] 计划列表（分类板块展示，可编辑 + 新建 + 删除）
- [x] 调度器 & 提醒闭环（Server酱推送到微信）
- [x] AI 问答：对话式创建/修改/删除任务（千问 tool calling）
- [ ] 独立 Bot（微信等渠道，脱离网页也能随手记）
- [ ] 每日早晚心跳（清单 + 复盘）
- [ ] 部署到常开的服务器，调度器脱离本地电脑运行
- [ ] v3：多用户

## 状态

开发中 — 先做给自己用，成熟后考虑开放给更多人。
