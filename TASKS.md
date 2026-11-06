# TASKS.md —— 任务清单（唯一待办事实来源）

> 规划者开工先读本文件，收工更新本文件。
> 完成后必须写 commit hash。不要只写"已完成"，要写**做成了什么**。

---

## 进行中

（无）

---

## 待办

### P1

- [ ] **TASK-007 ABDM 真机验证与降级策略**
  - 目标：确认 ABDM 能否真正落盘；若该版本不支持，界面给出明确降级提示
  - 背景：实测 ABDM 对 REST `POST /start-headless-download` 返回 200 但任务不入队，CLI 也静默失败（详见 PROJECT.md 第 5 节）
  - 卡点：需要用户先在 ABDM「设置 → 集成」里开启集成

- [ ] **TASK-009 只重试失败的订阅**
  - 目标：网络抖动导致部分失败后，不用整体重来
  - 涉及：记录上一次批量更新的失败列表，加一个"重试失败项"入口

- [ ] **TASK-018 订阅"有新版"时行内显示版本对比**
  - 目标：检查更新后，订阅行右侧显示「已装 v1.2 / 最新 v1.3」，而不只是一个「有新版」标签
  - 涉及：`_build_sub_row` 的 `check_state` 角标；`_latest_tag_of` 返回的 tag 存进 `sub['latest_tag']`

### P2

- [ ] **TASK-010 右键菜单禁用态更清楚**
  - 无历史版本时，菜单项应显示为灰色不可点（现在是"无历史版本"文字项）

- [ ] **TASK-011 搜索支持版本号**
  - `_candidate_visible` 目前匹配名称/作者/路径，加 version

- [ ] **TASK-012 备份列表显示差量**
  - 每个备份比当前 user_api 多了/少了几个音源

### P3（工程债）

- [ ] **TASK-013 BaseApp 拆分**
  - 2000+ 行 / 100+ 方法，可按关注点拆 Mixin（备份 / 订阅 / 设置 / 导入）
  - 风险：MRO 顺序，必须逐个验证

- [ ] **TASK-014 清理死代码**
  - `_extract_js_from_zip` 现只有自检在用，可合并进 `_extract_asset_main`

---

## 已完成

- [x] **TASK-017 订阅按需勾选更新 + 推荐音源多选导入**（v1.2.0）
  - 订阅卡每行加复选框；勾中后主按钮文案变「更新所选(N)」，未勾时仍是「一键更新」（更新全部）
  - 「选择 ▾」菜单：全选 / 全不选 / 只勾「有新版」的 / 勾选全部「已最新」的
  - 「检查更新」也遵守勾选范围，只检查勾中的；勾选集合在刷新时自动修剪越界索引
  - 「★ 推荐」改为弹出选择窗（`_view_pick_recommended`，纯 tk 实现，CTk/ttk 两套界面通用）：9 条内置音源逐条勾选，已订阅的置灰标注且默认不勾
  - 推荐表：pdone/lx-music-source 的 lx / xinghai / hyw / changqing / yuningxi / sixyin 六条 + Huibq/keep-alive + cdyUuu/lx-music-xinghai-source + wzh15802/lxmusic

- [x] **TASK-016 界面重塑：三套配色 + DPI 字号 + 缩放不黑屏 + 顶栏去齿轮**（v1.2.0）
  - 新增 `THEMES` 三套配色（暖砂 claude / 清风 green / 暗夜 dark），`apply_theme()` 原地更新 `PALETTE` 与 `LOG_COLORS`，切换后无需重启即可全局生效
  - 根因修复「全屏字好小」：新增 `_dpi_scale()`（`SetProcessDpiAwareness` + `GetDeviceCaps(88)`，实测本机 1.5），`ui_scale = 用户字号倍数 × 系统 DPI`，并关闭 CTk 自动缩放避免双重放大；150% 屏上字号从 12/13px 恢复到 18/20px
  - 设置窗新增「一、外观与行为」：配色下拉 + 字号滑块（0.85~1.6，实时百分比）+ 应用（提示重启界面生效）+ 洛雪程序路径选择
  - 右上角 ⚙ 删除，改为「设置 ▾」下拉菜单（外观与行为 / 重新定位数据文件 / 打开数据目录 / 检查工具更新 / 重启工具界面）
  - 底部三卡改「标题行 / 按钮行 / 列表行」三行 + 行权重，修卡片标题被按钮压住、缩放时黑块与底部写死（`<Configure>` 去抖后重设滚动区）
  - 四张卡的空态全部重做（居中盒 + 图标式标题 + 说明 + 主按钮），修左卡空态三行文字被 pady=40 裁掉

- [x] **TASK-015 下载进度可视化 + 一键重启洛雪 + 工具自身更新检查**（v1.2.0）
  - 新增状态栏进度行：`_dl_begin/_dl_update/_dl_end/_dl_tick` + `_view_set_progress`（未知总长走跑马灯，已知显示百分比与 `810.5 KB/976.6 KB`），每 25% 补一条日志；IDM/ABDM 失败会先写日志再回退下一方式——解决反馈 4「不用 IDM 就不知道在不在下载」
  - 顶栏「重启洛雪」：`do_restart_lx_music()` 结束进程后重新拉起；「检查更新」：`do_check_app_update()` 比对 `Heccdod/lx-music-source-manager` 的 Latest Release
  - 修 `_cand_state` 引用 `SourceScript.script` 导致 `AttributeError: 'SourceScript' object has no attribute 'script'`；改为解压后比 CRC32，新增四态角标（新 / = / ↑同版异内容 / ↑可升级 / ↓降级）
  - 「智能勾选」只勾新音源与可升级版本，跳过已装同版

- [x] **TASK-006 修复订阅版本标记不保存**（commit `5f69da6`）
  - 根因：`report['added']` 元素是一元组 `(s,)`，三处日志循环写成 `for s in ...: s.name` 抛 `AttributeError`，异常发生在 `sub['last_tag'] = tag` 之前
  - 修复：改为 `for s, in report['added']`
  - 附带：同名音源多版本按 `version_key()` 只保留最高版本

- [x] **TASK-005 界面减法与架构瘦身**（commit `723a241`）
  - 列表行 5 控件 → 2 控件；移除淡入动画；字号统一；去冗余列标题

- [x] **TASK-004 支持 AB Download Manager**（commit `b7642c1`）
  - 下载方式：自动 / 内置 / IDM / ABDM，自动模式逐级回退
  - 探测到 `ABDownloadManagerCli.exe`，REST + CLI 双路径

- [x] **TASK-003 订阅支持仓库目录来源**（commit `0bf2994`）
  - 支持不走 Release 的仓库，可指定子目录与分支，以提交短 sha 作版本标记

- [x] **TASK-002 订阅版本管理**（commit `8b1b15c`）
  - 旧版本移到 `history/<tag>/`，根目录只留最新；右键切换历史版本

- [x] **TASK-001 项目初始化**（commit `5c9636f` 起）
  - 导入 / 更新 / 备份 / 还原 / 订阅 / 设置页 / 双 UI

---

## 版本历史

| 版本 | 日期 | 内容 |
|---|---|---|
| v1.2.0 | 2026-11-06 | 订阅勾选更新、推荐音源多选、三套配色、DPI 字号、缩放修复、下载进度、重启洛雪、自身更新检查 |
| v1.1.1 | 2026-11-05 | 修复 last_tag 不保存 |
| v1.1.0 | 2026-11-05 | 订阅版本管理、仓库目录来源、ABDM、界面减法 |
| v1.0.2 | 2026-08-14 | 空 zip / 备份目录 / IDM 回退 / ttk 崩溃 |
| v1.0.1 | 2026-08-14 | 解压删压缩包、加密 zip |
| v1.0.0 | 2026-08-14 | 首个正式版 |
