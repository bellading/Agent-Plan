# AgentPlan

> 一个帮你**决定**、而不只是帮你**记住**的个人任务分诊 agent。

![status](https://img.shields.io/badge/status-building-orange) ![python](https://img.shields.io/badge/python-3.11+-blue) ![license](https://img.shields.io/badge/license-MIT-lightgrey)

信息太多、看到 A 又惦记 B、来回穿插，最后哪件都做不好——这个项目把"现在到底该做什么"从脑子里搬出来。你随手发一句话，它整理成任务、判断轻重缓急、到点提醒你，做完归档、没做完自动回流。

## 核心机制

你发一条 → AI 解析出「主题 + 备注」→ 按「重要 × 紧急」分诊成 **立即 / 排期 / 日常化 / 舍弃** → 结合你的重心和空闲排好提醒 → 到点提醒（可"过会再戳"或"记为未完成"）→ 完成沉淀、未完成回流 → 每天早晨推清单、晚间复盘。

所有判断都是 **AI 先猜、你一键确认或修改**，尽量不给录入增加负担。

## 功能（v1）

- 随手输入，自动拆「主题 / 备注」并归类（工作学习 / 生活 / 健身健康 / 自定义）
- 基于个人目标与空闲的智能分诊与优先级建议
- 定时提醒 +「贪睡」/「记为未完成」
- 每日早晨清单、晚间复盘，一周七天；特殊日可临时调整
- 目标型任务（如"X 天塑形"）自动生成计划并存入备注
- 低优先事项拖满 3 天主动问是否剔除；任务超 20 件提醒精简

## 架构

- **后端**：Python + SQLite，一个常驻调度器负责到点触发
- **智能层**：LLM 负责解析、分诊、复盘建议，结构化 JSON 输出
- **双客户端，共用一个后端**
  - 网页表格页（主场）：查看 / 勾选 / 编辑所有计划
  - Bot（辅助，后续接入）：随手输入 + 到点提醒

提醒通道做成可插拔接口：面向国内使用，走 **Server酱 / PushPlus 转发到微信**（服务号模板消息）或企业微信机器人，不依赖 Telegram；网页本身负责查看和操作，不承担推送职责。

## 数据模型（核心表）

| 字段 | 说明 |
|---|---|
| title / notes | AI 提炼的主题 / 备注（链接、生成的计划）|
| category / type | 分类 / 单件事 `single`·目标型 `goal` |
| importance · urgency | 各 high·med·low，AI 先猜 |
| action | 分诊结果：now / schedule / routine / drop |
| status | todo / doing / done / missed / routine / dropped |
| remind_at · snooze_until | 提醒时间 / 贪睡到点 |

## 本地运行

```
pip install -r requirements.txt
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

## Roadmap

- [x] 数据模型 & 分诊 prompt
- [x] 表格页（可编辑 + 新建任务）
- [x] 调度器 & 提醒闭环（Server酱推送到微信）
- [ ] Bot：录入 → 分诊 → 存储闭环
- [ ] 每日早晚心跳（清单 + 复盘）
- [ ] 部署到常开的服务器，调度器脱离本地电脑运行
- [ ] v2：多用户、目标型任务拆成循环提醒

## 状态

开发中 — 先做给自己用，成熟后考虑开放给更多人。
