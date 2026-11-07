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

- [x] **TASK-022 主题顺序与命名调整（默认「清风（洛雪）」）+ README 版权保护声明完善 + EXE 打包与 Git 提交**（v1.2.1，commit `8258658`）
  - 调整 `THEME_ORDER = ['green', 'claude', 'ocean', 'dark']` 与四套主题显示名称：`清风（洛雪）` / `暖砂（类Claude）` / `鲸蓝（类Deepseek）` / `星月（暗夜）`
  - 默认主题改为 `green`（`清风（洛雪）`），同步更新 `DEFAULT_SETTINGS['theme']`、`apply_theme` 默认回退值与自检断言
  - 更新 `README.md` 与源码头部文档，明确标注非官方开源爱好者作品声明、与洛雪官方/Anthropic/DeepSeek 无关联声明、色彩风格描述性说明及 OFL-1.1 开源字体许可声明
  - 使用 PyInstaller 重新构建单文件免安装 `LXmusic一键导入和更新.exe`（绑定 `lx_icon.ico` 洛雪图标并设置 `Medium` 完整性级别）并同步提交至 Git 仓库

- [x] **TASK-021 空状态水平垂直双居中 + 星夜靛蓝深色配色 + 无边框顶栏拖拽修复与缩放零卡顿 + 洛雪 EXE/任务栏专属图标**（v1.2.1）
  - **解决反馈一（空状态模块出现在所属布局左上方，改为居中）**：
    - 根因：`SmoothScrollableFrame._flush_canvas_fit` 原先无参调用了 `CTkScrollableFrame._fit_frame_dimensions_to_canvas()`（该方法签名需要 `event` 参数，抛 `TypeError` 被静默吞掉），导致 Canvas 内嵌窗口维持左上角 `(0, 0)` 收缩态
    - 修复：直接通过 `_parent_canvas.itemconfigure(_create_window_id, width=cw, height=ch if _empty_mode else 0)` 让空态下的内嵌 Frame 撑满 100% 画布宽高，并在 `_view_refresh_candidates`、`_view_refresh_imported`、`_view_refresh_backups`、`_view_refresh_subscriptions` 中统一使用 `box.place(relx=0.5, rely=0.5, anchor='center')` 实现水平与垂直双居中
  - **解决反馈二（暗夜模式橘色突兀，换用柔和配色）**：
    - 将 `THEMES['dark']` 从刺眼的暖橘/焦褐底色升级为**星夜靛蓝（Starlight Indigo / Moonlight Slate）**配色方案：深星夜蓝背景 `#13151c`、石板蓝卡片 `#1b1e28`、星光靛蓝主色 `#6e82f5`（悬停 `#5b70e8`）、柔和浅灰蓝正文 `#e6e9f2`，视觉柔和不刺眼；同步更新暗夜模式左上角星月徽标配色
  - **解决反馈三（修复顶栏无法拖拽 + 消除放缩和全屏卡顿）**：
    - **修复顶栏拖拽**：移除 `WS_CAPTION` 后 Windows `DefWindowProcW` 会忽略 `WM_NCLBUTTONDOWN + HTCAPTION`；改为在 `header`、`header._canvas`、左侧图标与主副标题上统一绑定 `<ButtonPress-1>`（`GetWindowRect` 记录偏移）+ `<B1-Motion>`（Win32 `SetWindowPos(..., SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)` 零延迟移动窗口）
    - **消除全屏与缩放卡顿**：移除 `_after_resize` 中动态调用 9 个 `CTkFont.configure(size=...)` 引发的近百个控件同步重绘冻结（约 500ms 卡顿），直接将基础字号升级到位（`FONT_BASE` 全面上调 1~2pt）；将主界面内 17 个纯布局透明 `CTkFrame(fg_color='transparent')` 替换为零 Canvas 开销的原生 `tk.Frame`，并为 6 张外层圆角卡片挂载 `_throttle_ctk_frame_redraw`（42ms 节流重绘圆角边框）
  - **解决反馈四（打包成 exe 后的文件图标与任务栏图标固定为“洛雪”主题图标）**：
    - 新增 `_ensure_lx_ico()`、`_apply_taskbar_and_window_icon()`、`_apply_win32_hwnd_icon()` 与独立 `AppUserModelID`（`lxmusic.source.manager.v2`）：自动在项目目录生成包含 `16x16 ~ 256x256` 7 档尺寸的 `lx_icon.ico`（洛雪主题翠绿双音符+六角雪晶图标），窗口与任务栏图标始终固定为“洛雪”图标（即使切换界面主题也不变，左上角徽章则随主题切换），打包 exe 时可直接指定 `--icon=lx_icon.ico`

- [x] **TASK-020 一体化无原生标题栏窗口 + 四主题专属徽标切换 + 小屏防遮挡布局 + 全屏大字号加成 + 缩放防抖提速**（v1.2.1）
  - **解决反馈一（清除顶部冗余系统标题栏）**：
    - 通过 Win32 `SetWindowLongW(hwnd, GWL_STYLE, style & ~WS_CAPTION)` 移除冗余的 Windows 原生顶部标题栏，同时完整保留任务栏图标、Win11 原生圆角阴影（`DwmSetWindowAttribute` 同步主题背景色）与四边/四角原生拖拽缩放（`WS_THICKFRAME`）
    - 主页面顶栏集成原生拖拽移动（`WM_NCLBUTTONDOWN + HTCAPTION`，支持 Win11 贴靠布局）、双击工作区最大化/还原（`SPI_GETWORKAREA`，不遮挡任务栏），以及右侧 `[─] [□] [✕]` 窗口控制按钮
  - **解决反馈二（切换主题时左上角图标同步切换专属形象）**：
    - 重写 `_make_icon(zoom, theme)`，支持四套主题各自独立的 4x 超采样矢量徽标，并在 `_view_rebuild_live` 中同步刷新左上角图标与系统任务栏图标：
      - `claude`（暖砂）：Claude 经典十二芒星徽章
      - `green`（清风 · 洛雪）：翠绿底板 + 洛雪双连八分音符 `♫` 与六角雪晶徽章
      - `ocean`（鲸蓝 · DeepSeek）：深海蓝底板 + 灵动喷水小鲸鱼（饱满鲸身、上扬双叶尾鳍、胸鳍、深蓝眼点与头顶水珠）
      - `dark`（暗夜）：深曜石金边底板 + 几何弯月与双星徽章
  - **解决反馈三（小屏下备份文件、订阅更新等标题被按钮覆盖）**：
    - 根因：原卡片头部使用 `grid` 且第 0 列标题 `weight=1`，窗口变窄时 Tkinter 优先把第 0 列压缩至 0px 并让第 1 列按钮直接盖在标题文字上；同时订阅卡顶栏塞入 6 个按钮导致超宽
    - 修复：所有卡片头部（`待导入音源`、`已导入音源`、`备份文件`、`订阅更新`、`运行日志`）改为 `pack` 布局且**标题最先 `pack(side='left')` 占位**，从布局算法上保证按钮绝不可能覆盖标题；将订阅卡的 `检查`、`拉取挑选`、`一键更新` 下沉至底栏右侧（顶栏仅留 `★ 精选源库`、`＋ 添加`、`选择 ▾`）；移除底部三卡 `uniform='bot'` 强制挤压并修正 `_view_rebalance_bottom` 权重为 `3 : 5 : 4`
  - **解决反馈四（全屏下字号即使开到最大仍然偏小）**：
    - 提升 `FONT_BASE` 桌面基准字号（`title=19, card=15, base=13, small=12, tiny=11`），上限开放至 `200%`（顶栏 `字号 ▾` 新增 `150%`、`180%` 档位）
    - 新增 `_viewport_font_boost(width)` 全屏/大窗口自动阅读加成：在 2.5K/4K 全屏或大窗口下自动叠加 `1.08x ~ 1.28x` 字号放大系数
  - **解决反馈五（拖拽缩放窗口时卡顿明显）**：
    - 根窗口改用专属 `RootOnly` bindtag（`bind_class('RootOnly', '<Configure>', ...)`），在 Tcl/Tk C 层过滤掉约 300 个子控件在缩放时的冒泡回调
    - 重写 `SmoothScrollableFrame` 的 `_parent_canvas` 与内部 Frame `<Configure>` 绑定为 `28ms/32ms` 节流防抖，避免拖拽窗口边框的每个像素都同步重排上百行音源列表

- [x] **TASK-019 `dsh-claude-style` 深度视觉与性能重构（Anthropic 字体体系 + 悬浮圆角弹出菜单 + 胶囊导入模式 + 60fps 丝滑防卡顿）**（v1.2.1）
  - **解决反馈「字体不好看（把 Anthropic 的字体搬过来）」**：
    - 从本机 `dsh-claude-style` 提取 `InterVariable.ttf`（Anthropic Sans Web Text）、`NotoSerifVariable.ttf`（Anthropic Serif Web Text）、`JetBrainsMonoVariable.ttf`（Anthropic Mono Web）落盘至 `config/fonts/`，启动时通过 Windows GDI `AddFontResourceExW(..., FR_PRIVATE, 0)` 免安装注入进程
    - 建立三层字体体系：标题与卡片抬头采用 `Noto Serif SC SemiBold`（Editorial 衬线感），正文与按钮采用 `Noto Sans SC` / `Noto Sans SC Medium`，版本号、统计徽章、路径与运行日志采用 `JetBrains Mono` 等宽字体
  - **解决反馈「更多等下拉列表很难看」**：
    - 彻底废弃原生 Win32 方框灰底 `tk.Menu` 与生硬的 `CTkOptionMenu`，新增 `_show_claude_popover` 自绘无边框 12px 圆角悬浮弹出卡片（复刻 `.dsh-claude-popover-card`），带 `#e8e4dc` 细描边、`#ede8dd` 柔和悬停圆角底板、`1px` 分割线以及 `#d97757` 陶土色当前选中勾号 `✓`
    - 顶栏 `主题`、`字号`、左卡 `选择 ▾`、订阅卡 `选择 ▾`、`镜像: ▾`、`下载: ▾` 以及所有列表行的右键上下文菜单全部统一为 Claude 悬浮圆角弹出卡片
  - **解决反馈「导入模式很奇怪，参考 dsh-claude-style 做」**：
    - 移除原先在左卡底部突兀占一整行的 `导入模式：[导入模式（直接新增） | 更新模式（同名更新）]`，改为在左卡底栏左侧内嵌 `dsh-claude-style` 下沉式胶囊拨片开关 `[ 仅新增 | 同名更新 ]`，与右侧 `导入所选`、`一键全部导入` 合一为单行紧凑操作栏
  - **复刻 `dsh-claude-style` 视觉语言细节**：
    - 精确对齐 `dsh-claude-style/docs/STYLE.md` 四套主题色值（暖砂 `#f5f2eb` / `#fcfbf8` / `#d97757`、清风、鲸蓝 DeepSeek、暗夜 `#171614`）
    - 4 倍超采样抗锯齿绘制 Claude 12 芒星徽标（`_make_icon`）与药丸状态徽章（`★ 新源`、`↑ 升级`、`= 同版`、`↓ 旧版`、`拉取挑选`）
  - **解决反馈「而且有点卡」**：
    - 列表复选框改为预渲染缓存的 4 倍超采样 `PhotoImage`（`_get_checkbox_images` + `_make_fast_check`），消除每行独立 `tk.Canvas` 带来的数百个画布重绘开销
    - 列表行悬停引入行级防抖状态（`_hovered_cand` / `_hovered_imp`）与 `_cur_bg` 短路判断，鼠标在同行子控件间移动不再触发全行 `.configure(bg=...)` 重绘，且保留胶囊徽章底色（`_keep_bg`）
    - 修复 `<Configure>` 窗口缩放卡顿：过滤非根窗口事件与相同尺寸事件，移除缩放过程中动态 `.configure(size=...)` 引发的整棵控件树重排；`SmoothScrollableFrame` 升级至 60fps（`FRAME_MS = 16`）

- [x] **TASK-018 人类审美视觉重构 + 订阅「拉取挑选」工作流 + 双分区精选源库 + 实时主题字号切换**（v1.2.0）
  - **解决反馈 1（订阅只能检查或强制全量导入）**：新增 `do_fetch_sub_to_candidates`（「拉取挑选」按钮、订阅行内 `[拉取挑选]` 快捷入口、右键菜单），支持将订阅仓库的最新音源下载解压并直接加载进左侧「待导入音源」候选列表，配合「智能勾选」自由挑选想要导入的音源，不再强制写入 `user_api.json`
  - **解决反馈 2（界面丑、全屏字小、右上角花哨齿轮、控件错位裁切）**：
    - 重调 4 套人类审美配色方案（`claude` 暖砂 Claude 风格、`green` 清风洛雪绿、`ocean` 晴空现代蓝、`dark` 暗夜深色），所有卡片增加细腻 `1px` `card_border` 描边与 `10px` 圆角
    - 实现 `_view_rebuild_live()` 原地实时重建界面，顶栏提供 `主题 ▾` 与 `字号 ▾`（100%/110%/120%/135%）快捷菜单，切换配色与字号**无需重启进程立即生效**
    - `_btn()` 按文案长度与当前字号自动推算安全最小宽度，彻底消除 150% DPI 下按钮文字被裁成半截（如「丁开文件」「一键更」）的问题
    - 自绘带 `⌕` 图标与 `✕` 清空按钮的搜索框，修复 CTk 6.0 关闭自动 DPI 时 `CTkEntry` 占位提示空白消失的问题；修复「导入模式」分段按钮轨道底色与卡片融为一体的问题；重绘 `WebCheck` 复选框边框对比度与对勾粗细
    - 底部三张卡片（`备份文件`、`订阅更新`、`运行日志`）统一为单行标题+操作栏，内部列表框水平严格对齐；订阅卡底部去掉溢出的裸 `tk.Entry`，改为整洁的加速镜像下拉预设（含自定义镜像弹窗）与下载方式下拉
  - **解决反馈 3（150% DPI 窗口溢出屏幕 + 缩放黑块 + 全屏字太小）**：
    - 修复 `_dpi_scale()` 与 `_initial_size()` 在 150% DPI（逻辑分辨率 `1707x1067`）下重复乘 1.5 导致初始窗口 `1860x1230` 超出屏幕的严重 bug
    - `<Configure>` 缩放防抖重绘时同步 Canvas 背景色防止黑块残影，并在全屏/大窗口（`w >= 1380` / `1520`）时动态微调放大字号，解决全屏字小问题
  - **解决反馈 4（内置下载无提示）**：状态栏内嵌实时下载进度条与百分比/体积速率展示，每 25% 写入日志反馈
  - **解决反馈 5（内置精选音源库升级为双分区）**：`★ 精选源库` 弹窗升级为上下双分区——上半区「🔥 热门单源直链（免订阅 · 多镜像自动回退）」（内置星海、HYW、LX v7、长青 SVIP、六音、玉宁熙 Pro、Huibq 公益源共 7 款，默认预勾「黄金三件套」并支持 `ghproxy.net` / `gh.llkk.cc` / `gh-proxy.org` / `ghfast.top` 自动回退拉取到左侧候选区或一键导入），下半区「📦 活跃音源仓库（添加长期订阅）」（含 `guoyue2010/lxmusic-`、`pdone/lx-music-source`、`cdyUuu/lx-music-xinghai-source`、`Huibq/keep-alive`、`wzh15802/lxmusic` 等）
  - **订阅行内版本对比**：检查更新后直接显示 `已装 vX → 最新 vY` 及 `↑ 有新版` / `✓ 最新` 状态角标

- [x] **TASK-017 订阅按需勾选更新 + 推荐音源多选导入**（v1.2.0，commit `b97d2ff`）
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
