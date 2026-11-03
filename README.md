# AgentPlan

> 一个帮你**决定**、而不只是帮你**记住**的任务分诊 agent，多人可用。

![status](https://img.shields.io/badge/status-building-orange) ![python](https://img.shields.io/badge/python-3.11+-blue) ![license](https://img.shields.io/badge/license-MIT-lightgrey)

信息太多、看到 A 又惦记 B、来回穿插，最后哪件都做不好——这个项目把"现在到底该做什么"从脑子里搬出来。你随手发一句话，它整理成任务、判断轻重缓急、到点提醒你，做完归档、没做完自动回流。现在支持多人各自注册账号使用，彼此数据完全隔离。

## 核心机制

打开"AI 问答"，随便聊你要做的事——AI 不会你一说"我要xxx"就立刻建一条任务，而是先追问清楚重要紧急程度、尤其是**时间**（这个必须问清楚，不会瞎猜，知道今天的真实日期），目标型的事还会给一个具体可执行的计划建议。给出计划后先问"满意/不满意"，不满意可以继续提修改意见、反复调整直到满意，满意后再问"加入/不加入"计划表，确认加入才真正创建（一个计划如果拆成好几个子任务，会分别建好几条，不会漏）。"计划列表"按 学习/工作/运动/食物/其他 分板块展示所有任务，可以直接编辑或删除。到点提醒发邮件通知。

## 功能（v3：多用户）

- **账号系统**：注册/登录，每个账号的任务、分类、AI 对话完全互相隔离，谁也看不到、改不到别人的数据；左下角头像菜单可以设置自己的提醒邮箱、退出登录
- **AI 问答**：
  - 对话式创建/修改/删除任务，时间不清楚会主动追问，目标型任务给具体计划建议（不是一句话进、任务立刻出）
  - 展示计划后先问"满意/不满意"，不满意可以继续提修改意见、反复调整直到满意，满意后再问"加入/不加入"计划表，确认加入才真正创建；计划里如果有多个子任务，会按需要分别创建，不止建第一个
  - 支持多个独立对话（类似聊天记录分组）：左侧有会话列表，"+"新开一个，按最近活跃时间排序，每个会话可以单独删除
  - 回复里的链接可以直接点开，支持 Markdown 渲染（标题/加粗/列表）；每条消息下面有时间和复制按钮，AI 的回答还有 👍/👎；生成较长时可以点"停止"中断
- **计划列表**：先看到分类色块（学习/工作/运动/食物/其他 + 一个"+"自定义，每人独立），点进某个分类才看到里面的任务卡片，每个字段都能直接编辑，支持删除
- **定时提醒**：到点自动发邮件到每个人自己设置的提醒邮箱，互不干扰
- 手动新建任务的入口依然保留（不想聊天时快速记一条）

## 架构

- **后端**：Python (Flask) + SQLite，账号/任务/分类/对话全部以 `owner_id` 隔离；生产环境用 gunicorn（单 worker 多线程）启动，提醒调度器作为后台线程跟着同一个进程跑，不需要单独部署
- **智能层**：通义千问（Qwen，走阿里云百炼/DashScope），带 tool calling——AI 问答里创建/修改/删除任务都是它主动调用 `create_task`/`update_task`/`delete_task`/`list_open_tasks` 这几个工具完成的，不是一次性把整段话解析成 JSON；服务端会校验工具调用顺序（不能跳步、不能在没确认的情况下直接创建），杜绝模型在没真正执行的情况下自己编"已完成"
- **网页三块，共用一个后端**：登录/注册、AI 问答（聊天，支持多会话）、计划列表（按分类分板块，可编辑可删除）
- **提醒通道**：邮件（Gmail SMTP），每个账号可以单独设置自己的提醒邮箱；原来的 Server酱/微信推送代码还在（`notifier.send_wechat`），适合单人部署时使用

## 数据模型（核心表）

| 表 | 说明 |
|---|---|
| users | 账号：用户名、密码（加密存储）、提醒邮箱 |
| tasks | owner_id · title/notes · category · type（`single`/`goal`）· importance/urgency（high/med/low）· action（now/schedule/routine/drop）· status · remind_at/snooze_until |
| categories | owner_id · 分类名 · 排序，每人独立 |
| chat_conversations | owner_id · AI 问答的会话分支，标题取自第一条消息 |
| chat_messages | owner_id · conversation_id · role · content · feedback（👍/👎）· action_type（满意/加入确认流程用） |

## 部署上线（Render）

目前部署在 Render（gunicorn，单 web service，提醒调度器作为后台线程跟着跑，不需要单独的 worker 服务）：

1. Render 建 Web Service，连到这个仓库，分支 `claude/great-turing-mjkh2v`，会自动识别 `Procfile`
2. 加一块持久化磁盘（Disk，免费套餐不支持，需要付费实例类型），挂载路径 `/data`
3. 环境变量：
   - `DASHSCOPE_API_KEY`：通义千问 API Key
   - `AGENTPLAN_DB_PATH`：`/data/agent_plan.db`（配合第 2 步的磁盘）
   - `FLASK_SECRET_KEY`：一个随机字符串，用来签名登录 session
   - `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD`：发提醒邮件用的 Gmail 账号和应用专用密码（不是登录密码，需要先在 Google 账号开 2 步验证后生成）

⚠️ **免费套餐没有持久化磁盘**：没加磁盘的话，每次重新部署（包括每次推代码）数据库都会被清空（所有账号、任务、聊天记录），需要重新注册。想长期保留数据得升级到支持磁盘的付费实例。

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
- Windows：双击 `start_windows.bat`——网页会在后台最小化运行（不会弹出来挡着），只在任务栏能看到"AgentPlan Web"图标；要停止就去任务栏把这个窗口关掉，或者用任务管理器结束对应的 python 进程；如果网页打不开想看报错，点开任务栏里"AgentPlan Web"那个窗口就能看到。提醒调度器现在跟着网页一起跑，不用再单独开一个脚本

不想用脚本、想自己在终端里跑也可以：

```
python3 app.py          # 网页：http://127.0.0.1:5000（提醒调度器作为后台线程一起启动）
```

第一次打开会先看到"设置密码"页面，注册一个账号即可开始用。

### 配置提醒邮件（Gmail）

1. 打开你的 Google 账号，确认开了"两步验证"：https://myaccount.google.com/signinoptions/two-step-verification
2. 生成一个应用专用密码：https://myaccount.google.com/apppasswords （选 Mail / 自定义名称）
3. 二选一保存：
   - `export GMAIL_ADDRESS=you@gmail.com` + `export GMAIL_APP_PASSWORD=xxxx`（每次开终端要重新设置）
   - 或存到 `.secrets/gmail_address.txt` / `.secrets/gmail_app_password.txt`（已加入 .gitignore，不会被提交，重启后依然有效）
4. 不配置时调度器只会在终端打印"本该发送"的内容，不会报错，方便先跑通逻辑再接真实推送
5. 每个账号登录后，点左下角头像 →"设置提醒邮箱"，填自己想收提醒的邮箱（可以跟登录用户名不是同一个邮箱）

想用原来的微信推送（Server酱）也可以，`notifier.send_wechat()` 还在，适合单人部署场景，自己改 `scheduler.py` 调用它即可。

### 配置 AI 问答（通义千问）

"AI 问答"视图需要一个 API Key 才能对话：

1. 打开 https://bailian.console.aliyun.com/ ，开通百炼/DashScope，拿到一个 `sk-...` 开头的 API Key（当前用的是 qwen-max 模型——比 qwen-plus 贵一些，但多步骤指令遵循更稳定，调用频率是个人使用级别，差价不明显，想换回 qwen-plus 改 `llm.py` 里的 `MODEL` 常量即可）
2. 二选一保存：
   - `export DASHSCOPE_API_KEY=sk-...`
   - 或存到 `.secrets/qwen_api_key.txt`（已加入 .gitignore）
3. 没配置时聊天会返回报错提示，不影响"计划列表"里手动新建/编辑/删除任务

## Roadmap

- [x] 数据模型
- [x] 计划列表（分类板块展示，可编辑 + 新建 + 删除）
- [x] 调度器 & 提醒闭环（邮件）
- [x] AI 问答：对话式创建/修改/删除任务（千问 tool calling），支持多会话分支
- [x] v3：多用户账号系统，数据隔离
- [x] 部署到常开的服务器（Render）
- [ ] 修改密码 / 忘记密码自助找回
- [ ] 邀请制注册（现在任何人拿到链接都能自己注册）
- [ ] 独立 Bot（微信等渠道，脱离网页也能随手记）
- [ ] 每日早晚心跳（清单 + 复盘）

## 状态

多用户版本已部署上线，供小范围朋友使用。免费套餐暂不支持持久化存储，数据会随重新部署清空，使用中。
