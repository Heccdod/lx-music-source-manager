# AGENTS.md —— 多模型协作规约

> 本文件定义「谁做什么、怎么交接、怎么验收」。与 PROJECT.md 配套：
> **PROJECT.md 讲项目是什么，AGENTS.md 讲怎么协作。**

---

## 1. 角色定义

| 角色 | 模型 | 职责 | 禁止 |
|---|---|---|---|
| **规划者（Planner）** | Gemini 4 Argon（`antigravity/gemini-4-argon-high`） | 与用户沟通需求、拆解任务、写任务卡、派活、验收成果、决定是否继续迭代 | 不直接堆业务代码（可改文档/配置/小修补） |
| **编码者（Coder）** | DeepSeek V4.1 Flash（`workbuddy/deepseek-v4.1-flash`，0.11x） | 按任务卡实现代码、跑自检、写验证脚本、报告结果 | 不擅自扩大范围、不跳过验收 |
| **用户** | 人 | 提需求、拍板、最终验收 | —— |

### 1.1 规划者没有历史记忆

规划者每次开工都是"新人"。所以：

- 每次新会话，第一件事是**读 `PROJECT.md`**（项目宪法）+ **读任务清单**（见第 4 节）
- 不要指望它记得"上次那个 bug 修没修"，要靠文档记录
- 交接必须**写成文件**，不能只在对话里说

---

## 2. 任务卡（Task Card）格式

规划者派活给编码者时，任务卡必须是**自包含**的——编码者看不到规划者的对话，也看不到用户的原始需求。

```markdown
## TASK-<编号> <一句话标题>

**目标**：改完后用户能得到什么（一句话，用户视角）

**背景**：为什么需要这个改动。如果跟某个 bug 有关，贴关键报错/日志原文。

**涉及文件**：绝对路径 + 大致行号范围

**验收标准**：
- [ ] 编译通过
- [ ] `--selftest` 全绿
- [ ] <具体行为断言，比如"订阅行右侧显示当前 tag" >

**约束**：
- 必须遵守 PROJECT.md 第 3.2 节设计约定
- 不许改 <某个不该动的模块>

**交付物**：改动摘要 + 自检输出 + 验证脚本输出
```

> **反例**：任务卡里写"修一下订阅更新那个问题"——编码者不知道是哪个问题，会瞎猜。
> **正例**：贴上报错 `AttributeError: 'tuple' object has no attribute 'name'`，指出 `report['added']` 是一元组，要求三处循环改成 `for s, in`。

---

## 3. 派活方式

### 3.1 规划者派活给编码者

规划者调用子代理工具（DSH 的 `subagent`），并**指定模型**：

```
subagent(
  description: "<3-5 词概括>",
  prompt: "<完整任务卡，自包含>",
  provider: "workbuddy",
  model: "deepseek-v4.1-flash",
  reasoning_effort: "high"
)
```

要点：

- `provider` / `model` 必须显式写，否则可能继承到别的不允许的路由
- `prompt` 要**完整**，别写"接着刚才的思路"——子代理没有刚才
- 可以并行派多个独立任务（一条消息里发多个 `subagent` 调用）
- 子代理返回的是**结论**，不是过程；要过程就让它把输出写进文件

### 3.2 双向协作：规划者可以直接和子代理对话

派活不是「扔出去就不管」。子代理卡住时，规划者要**介入**，而不是等它失败后重派。

#### 可用的交互工具

| 工具 | 作用 |
|---|---|
| \`subagent(...)\` | 起一个子代理，返回 \`agentId\` |
| \`list_agents({scope: "children"})\` | 看子代理状态：\`running\`（在干活）/ \`inactive\`（闲着或已结束） |
| \`send_message({agent_id, message})\` | 给子代理发消息：**运行中**会在它的下一个 step 收到；**空闲**会开启新一轮 |
| \`interrupt_agent({agent_id})\` | 让它停下（方向错了就中断，别让它继续烧 token） |

#### 三种必须介入的情形

**① 子代理明确说卡住**

子代理回报"这个我不确定怎么做 / 试了 X 和 Y 都失败"，规划者要：
1. 自己想清楚方案（这是 Argon 该干的活——它更强）
2. 用 \`send_message\` 把**具体方案**发过去：伪代码、关键算法、要改哪几个函数、为什么之前的思路错
3. 让它继续，而不是重开一个子代理（重开就丢了它已经积累的探索）

**② 子代理的方案明显是错的**

读它的 diff / 看它的计划，发现方向错了：
- 方向还能救 → \`send_message\` 指出错在哪，给正确方向
- 方向完全歪 → \`interrupt_agent\` 中断，重新派一张更明确的任务卡

**③ 子代理反复失败（同一处改两三次还不对）**

说明任务卡里的信息不够。规划者要：
1. 自己先读那段代码（此时应该自己看了）
2. 把**完整的正确改法**写进任务卡（可以贴出目标代码片段）
3. 重新派活；或自己动手改这一处（见 3.3 的例外条款）

#### 双向协作的正确姿势

\`\`\`
规划者：subagent(任务卡) ────────────────→ 编码者
                                          ↓
编码者：「A 方案试了不行，B 方案也报错 xxx」← 回报
        ↓
规划者：send_message("改用 C：先取 last_tag 再写回，
                     注意 report['added'] 是一元组，用 for s, in 解包")
        ↓
编码者：按 C 改完，自检通过 ──────────────→ 回报
        ↓
规划者：自己跑一遍验证 → 通过 → commit
\`\`\`

**关键**：规划者提供的是**方案**（思路、伪代码、关键行），不是完整文件。
真正落盘编辑仍由编码者做——这样职责边界清楚，也便于验收。

### 3.3 例外：规划者什么时候可以自己写代码

默认规划者不写业务代码，但以下情况可以自己动手：

| 情况 | 允许 | 理由 |
|---|---|---|
| 改文档（PROJECT.md / AGENTS.md / TASKS.md / README） | ✅ 随时 | 本来就归规划者 |
| 改配置（billion-context.json、cordis.patch.yml） | ✅ 随时 | 属于环境搭建 |
| 修**一行以内**的明显笔误（拼错变量名、少个逗号） | ✅ | 派活的成本远高于自己改 |
| 子代理**连续两次**在同一处失败 | ✅ 可以自己改 | 已证明任务卡表达不清，再派也是浪费 |
| 需要判断力而非体力的改动（架构取舍、调参） | ✅ 可以自己改 | 这正是强模型的优势 |
| 大段业务逻辑实现 | ❌ 派给编码者 | 成本考量：Argon 贵 |

原则：**规划者的时间花在"想清楚"上，编码者的时间花在"写下来"上。**
遇到想不清楚的地方，规划者先想清楚，再决定是自己写还是派下去。

### 3.4 编码者的回报格式

```
**完成**：<一句话>
**改动**：<文件:行号> <做了什么>
**验证**：编译 ✓ / selftest ✓ / 行为断言 ✓（贴关键输出）
**未完成/风险**：<诚实说明>
```

---

## 4. 任务清单文件

项目根目录维护一份 `TASKS.md`，是**唯一**的待办事实来源：

```markdown
## 进行中
- [ ] TASK-007 一键更新的进度条

## 待办
- [ ] TASK-008 只重试失败的订阅

## 已完成
- [x] TASK-006 修复 last_tag 不保存（commit 5f69da6）
```

规则：

- 规划者开工先读它，收工更新它
- 完成后必须写 commit hash
- 不要只写"已完成"，要写**做成了什么**

---

## 5. 验收流程

```
编码者交活
   ↓
规划者自查（读 diff，不信任口头汇报）
   ↓
跑验收三件套（编译 / selftest / 行为验证）
   ↓
不通过 → 退回，附具体失败输出
通过   → 更新 TASKS.md → 决定是否 commit
```

**规划者必须自己跑一遍验证，不能只看编码者说"通过了"。** 曾经发生过：编码者说自检全绿，实际是它改了自检的断言。

---

## 6. 上下文管理（billion-context）

本机已装 `billion-context 0.1.212`，通过 DSH 插件生效：

- 配置文件：`C:\Users\28381\.config\billion-context\billion-context.json`
- 已设 `promptCache.routing = "auto"`（走账号池 relay 时必须开，否则前缀缓存随机 miss）
- 压缩阈值：`maxContextLimit 75%` / `emergencyThresholdPercent 95%`
- 会话日志：`C:\Users\28381\.local\state\billion-context\bili.log`

**规划者特别注意事项**：

- 规划者会话应该**短**——只做规划和验收，不读大段代码。让编码者读
- 如果规划者上下文快满，让它输出"当前决策摘要"到 `TASKS.md`，然后换新会话继续
- 压缩是自动的，不需要手动清理；但**不要把关键决策只留在对话里**

---

## 7. 子代理模型白名单（重要限制）

DSH 对子代理可用的模型有白名单限制，当前实测：

```
workbuddy — WorkBuddy
  workbuddy/deepseek-v4.1-flash — DeepSeek-V4.1-Flash · x0.11  ✅ 可用
  workbuddy/gemini-3.8-flash    ❌ not allowed for this Session
  workbuddy/deepseek-v4-pro     ❌ not allowed
```

**要放开限制**：DSH 设置 → **子智能体** → 「模型选择」→ 勾选"允许 Agent 为子智能体选择模型" + 添加路由。改完**重启 DSH** 生效。

Gemini 4 Argon 走的是独立 provider `antigravity`（agy CLI），模型 id：
`gemini-4-argon-high` / `gemini-4-argon-medium` / `gemini-4-argon-low`

---

## 8. 常用命令速查

```powershell
# 开发目录
cd 'C:\Users\28381\Documents\Default Project'

# 编译 + 自检
python -m py_compile 'LXmusic一键导入和更新.py'
python 'LXmusic一键导入和更新.py' --selftest
python 'LXmusic一键导入和更新.py' --selftest --force-ttk

# 同步到仓库副本
Copy-Item 'LXmusic一键导入和更新.py' 'C:\Users\28381\Documents\lx-music-source-manager\' -Force
Copy-Item 'PROJECT.md','AGENTS.md','TASKS.md' 'C:\Users\28381\Documents\lx-music-source-manager\' -Force

# 提交（带低速保护，避免网络卡 5 分钟）
cd 'C:\Users\28381\Documents\lx-music-source-manager'
git add -A
git commit -m "fix: ..." -m "正文"
git -c http.lowSpeedLimit=2000 -c http.lowSpeedTime=20 push origin main
```

---

## 9. 禁止事项

1. **不要凭记忆回答项目细节** —— 读文件
2. **不要跳过验收** —— 每次改动都要跑编译 + 自检
3. **不要在两套 UI 里各写一份业务逻辑** —— 放 BaseApp
4. **不要在后台线程弹对话框** —— 见 PROJECT.md 4.3
5. **不要用 `globals()` 打模块补丁** —— 用 `m.settings_path = lambda: ...`
6. **不要忘记修完整性级别** —— 打包后 `icacls /setintegritylevel Medium`
7. **不要把测试数据写进真实配置目录** —— 一律用 `tempfile.mkdtemp()`
8. **不要在仓库副本里直接开发** —— 改 Default Project，再同步
