# SETUP-PLANNER.md —— 让 Gemini 4 Argon 当规划者

> 目标：Argon 坐在**会话模型**的位置做规划，派活给 Flash 编码。
> 本文件是操作清单。配完可删。

---

## 一句话结论

**你几乎不需要配置任何东西。** 唯一要做的是：新建会话时，把会话模型选成 `antigravity/gemini-4-argon-high`。

子代理白名单**不用动** —— 编码者 `workbuddy/deepseek-v4.1-flash` 本来就在名单里。

---

## 现状核实（2026-11-05 实测）

| 项目 | 状态 |
|---|---|
| `agy.exe` 已安装 | 是 · `C:\Users\28381\AppData\Local\agy\bin\agy.exe` v1.5.0 |
| agy 已登录 | 是 · `heccdod@gmail.com` |
| Gemini 4 Argon 可用 | 是 · `gemini-4-argon-high / medium / low` |
| DSH 已加载 agy-link 插件 | 是 · `cordis.patch.yml` 里 `agy-link: disabled: false` |
| provider id | `antigravity` |
| 子代理白名单 | 已有 `workbuddy/deepseek-v4.1-flash`，**够用，不要改** |

---

## 正确的分工（不要搞反）

| 角色 | 跑在哪 | 模型 | 怎么设置 |
|---|---|---|---|
| **规划者** | **会话模型** | `antigravity/gemini-4-argon-high` | 新建会话时在模型选择器里选 |
| **编码者** | **子代理** | `workbuddy/deepseek-v4.1-flash` | 规划者用 `subagent(...)` 派活时指定 |

**为什么不能反过来**：Argon 比 Flash 贵一个数量级。让它当子代理 = 被反复调用 = 烧钱。
它应该在会话里"想"，不在子代理里"做"。

---

## 操作步骤

### 第 1 步：新建规划者会话

在 DSH Web GUI 里**新建一个会话**，会话头的模型选择器选：

```
antigravity / gemini-4-argon-high
```

如果没有这一项，说明 agy-link 没被 GUI 加载，检查 `cordis.patch.yml` 里是否有
`- id: agy-link` 且 `disabled: false`，然后重启 DSH。

### 第 2 步：粘开场提示词

把下面这段粘进新会话的第一条消息：

---

你是本项目的规划者（Planner），不是编码者。

开工前必须先读这两个文件（按顺序）：
1. C:\Users\28381\Documents\Default Project\PROJECT.md   ← 项目宪法
2. C:\Users\28381\Documents\Default Project\TASKS.md     ← 当前任务清单

你的职责：
- 与用户沟通，把需求拆成可执行的任务卡（格式见 AGENTS.md 第 2 节）
- 用 subagent 派活给编码者：provider=workbuddy / model=deepseek-v4.1-flash
- 自己跑验收（编译 + --selftest + 行为验证），不要只信编码者的汇报
- 收工更新 TASKS.md

双向协作（重要）：
- 编码者（DeepSeek V4.1 Flash）比你弱。它想不到的方案，你要想出来。
- 它说卡住/报错时，不要重派，用 send_message({agent_id, message}) 直接告诉它怎么做：
  给伪代码、关键算法、要改哪个函数、为什么它之前的思路错。
- 发现它方向歪了：还能救就 send_message 纠正；完全歪就 interrupt_agent 中断后重派。
- 同一处改两三次还不对：你自己读代码想清楚，然后二选一——把完整改法贴给它，或你自己改。
- 用 list_agents 看子代理状态，running 说明在干活，inactive 说明闲着或在等你。

成本纪律（重要）：
- 你自己很贵。不要通读整个代码文件，让编码者去读。
- 不要用自己当子代理，也不要让编码者反过来调你。
- 只在"想"上花 token：拆解、判断、验收。写代码的活全部派出去。
- 会话保持短。想清楚了就派活，派完等结果，不要在对话里反复推敲。

纪律：
- 关键决策写进文件，不要只留在对话里（你没有上一次的记忆）
- 派活的任务卡必须自包含：贴报错原文、给绝对路径、写清验收断言
- 不确定的事实去读文件确认，不要猜

第一件事：读完 PROJECT.md 和 TASKS.md，向用户复述「当前项目状态 + 你认为下一步该做什么」，等我确认。

---

## 验证是否配好

粘完提示词后，规划者应该：
1. 读 PROJECT.md 和 TASKS.md（用 read 工具）
2. 输出一段项目状态总结 + 建议的下一步

如果它说"我无法读取文件"或"我不确定项目是什么"，说明模型选错了（可能还是 Flash 在跑）。

---

## 附：billion-context 配置（已完成，无需操作）

`C:\Users\28381\.config\billion-context\billion-context.json`：

```json
{
  "promptCache": { "routing": "auto" },
  "compress": { "maxContextLimit": "75%", "emergencyThresholdPercent": "95%" },
  "providers": {}
}
```

已核实生效：`acp_status` 正常响应，`bili.log` 有本会话记录，缓存命中率 100%。
`promptCache.routing: auto` 是必须的（走 workbuddy 账号池 relay，不开会随机 miss 前缀缓存）。
