# SETUP-PLANNER.md —— 配置 Gemini 4 Argon 当规划者

> 目标：让 Gemini 4 Argon 当一个**无记忆的规划者**，派活给 DeepSeek V4.1 Flash 编码。
> 本文件是操作清单，照着点即可。配完可删。

---

## 现状核实（2026-11-05 实测）

| 项目 | 状态 |
|---|---|
| `agy.exe` 已安装 | ✅ `C:\Users\28381\AppData\Local\agy\bin\agy.exe` v1.5.0 |
| agy 已登录 | ✅ `heccdod@gmail.com`（凭据在 `~/.dsh/agy-accounts/`） |
| Gemini 4 Argon 可用 | ✅ `gemini-4-argon-high / medium / low` |
| DSH 已加载 agy-link 插件 | ✅ `cordis.patch.yml` 里 `agy-link: disabled: false` |
| provider id | `antigravity` |
| 当前子代理白名单 | ⚠️ 只有 `workbuddy/deepseek-v4.1-flash` |
| `antigravity` 能否当子代理 | ❌ `LLM provider "antigravity" is not allowed for this Session` |

---

## 操作步骤

### 第 1 步：放开子代理模型白名单（必须）

打开 DSH Web GUI：**http://127.0.0.1:53060**

```
设置（左下角齿轮）
  → 子智能体（Subagent）
    → 模型选择（"允许 Agent 为子智能体选择模型"）
      → 打开开关
      → 添加路由：
           provider: antigravity    model: gemini-4-argon-high
           provider: antigravity    model: gemini-4-argon-medium
           provider: workbuddy      model: deepseek-v4.1-flash   ← 保留，这是编码者
      → 保存
```

**改完必须重启 DSH**（白名单是会话级快照，不重启对已开会话无效）。

> 如果设置页找不到「模型选择」，说明该 DSH 安装的 `dsh-client-ui-settings-subagent` 版本较旧。
> 备选方案：直接编辑 profile 配置
> `C:\Users\28381\.dsh\profiles\desktop\cordis.patch.yml`，
> 在 `subagent-model-selection-settings` 条目下加 `config.allowedModels`（格式见 AGENTS.md 第 7 节），
> 然后重启。

### 第 2 步：验证白名单生效

重启后，在**任意**会话里让我（或规划者）执行：

```
list_subagent_models(provider: "antigravity")
```

预期输出包含 `antigravity/gemini-4-argon-high — Gemini 4 Argon (High)`。
若仍报 `not allowed`，说明白名单没生效，回第 1 步检查。

### 第 3 步：给规划者一个干净的开场

新建会话，**默认模型选 `antigravity/gemini-4-argon-high`**（会话头的模型选择器），
然后把下面这段粘进去：

---

```
你是本项目的规划者（Planner），不是编码者。

开工前必须先读这两个文件（按顺序）：
1. C:\Users\28381\Documents\Default Project\PROJECT.md   ← 项目宪法
2. C:\Users\28381\Documents\Default Project\TASKS.md     ← 当前任务清单

你的职责：
- 与用户沟通，把需求拆成可执行的任务卡（格式见 AGENTS.md 第 2 节）
- 用 subagent 派活给编码者，provider=workbuddy / model=deepseek-v4.1-flash
- 自己跑验收（编译 + --selftest + 行为验证），不要只信编码者的汇报
- 收工更新 TASKS.md

双向协作（重要）：
- 编码者（DeepSeek V4.1 Flash）比你弱。它想不到的方案，你要想出来。
- 它说卡住/报错时，不要重派，用 send_message({agent_id, message}) 直接告诉它怎么做：
  给伪代码、关键算法、要改哪个函数、为什么它之前的思路错。
- 发现它方向歪了：还能救就 send_message 纠正；完全歪就 interrupt_agent 中断后重派。
- 同一处改两三次还不对：你自己读代码想清楚，然后二选一——把完整改法贴给它，或你自己改（AGENTS.md 3.3）。
- 用 list_agents 看子代理状态，running 说明在干活，inactive 说明闲着或在等你。

纪律：
- 规划者会话要短。不要通读代码，让编码者去读
- 关键决策写进文件，不要只留在对话里（你没有上一次的记忆）
- 派活的任务卡必须自包含：贴报错原文、给绝对路径、写清验收断言
- 不确定的事实去读文件确认，不要猜
- 你的价值在"想清楚"，不在"写下来"。想清楚了再决定是自己写还是派下去

第一件事：读完 PROJECT.md 和 TASKS.md，向用户复述「当前项目状态 + 你认为下一步该做什么」，等我确认。
```

---

## 架构说明（为什么这样配）

```
用户
  ↓ 提需求
规划者 Gemini 4 Argon（antigravity）      ← 只规划，不写业务代码
  ↓ 任务卡（subagent provider=workbuddy model=deepseek-v4.1-flash）
编码者 DeepSeek V4.1 Flash × N（可并行）   ← 写代码、跑自检
  ↓ 回报结论
规划者验收（自己跑一遍编译 + selftest）
  ↓ 通过
提交 git + 更新 TASKS.md
```

**成本考量**：Argon 贵，只做规划（消耗小）；Flash 0.11x 便宜，干重活。
规划者会话保持短，是因为它没有记忆，长会话也不会让它变聪明，只会浪费 token。

**替代方案（如果白名单搞不定）**：

| 方案 | 做法 | 代价 |
|---|---|---|
| 单会话换模型 | 直接把当前会话模型切到 `antigravity/gemini-4-argon-high` | Argon 变成执行者，与"只规划"矛盾；但记忆连续 |
| 用 subagent_fork | 规划者用 `subagent_fork` 而不是 `subagent`，子代理能继承已完成轮次 | 子代理上下文膨胀，成本上升 |
| 纯人工接力 | 在 Argon 会话里规划 → 把任务卡复制到本会话 → 我（V4.1-Flash）执行 | 零配置，但需要人工搬运 |

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
