# PROJECT.md —— 项目宪法（所有接手模型必读）

> 本文件是这个项目的唯一事实来源。任何模型接手前必须先完整读一遍，不要凭猜测动手。
> 最后更新：2026-11-05 · 对应提交 `5f69da6`

---

## 0. 快速事实卡

| 项 | 值 |
|---|---|
| 项目名 | LX Music 音源一键导入 / 更新工具 |
| 形态 | 单文件 Python GUI 桌面程序（Windows），打包成免安装 exe |
| 主源码 | `LXmusic一键导入和更新.py`（约 4400 行，单文件，无包结构） |
| 仓库 | https://github.com/Heccdod/lx-music-source-manager |
| 本地开发目录 | `C:\Users\28381\Documents\Default Project`（从这里构建 exe） |
| 仓库副本目录 | `C:\Users\28381\Documents\lx-music-source-manager`（从这里 git push） |
| 运行环境 | Windows 10/11，Python 3.14.6（`D:\Program Files\Python314`），150% DPI |
| GUI 库 | customtkinter 6.0.0，失败时自动回退内置 ttk |
| 打包 | PyInstaller 6.21.0，`--onefile --windowed`，产物约 31 MB |
| 用户数据 | `%APPDATA%\lx-music-desktop\LxDatas\user_api.json` |
| 工具配置 | `<程序目录>/config/`（settings.json / subscriptions.json / backups/ / logs/app.log） |

**两个目录的关系**：`Default Project` 是开发/构建目录；改完后必须把 `.py` 复制到 `lx-music-source-manager` 才能 git 提交。**千万不要在仓库副本里直接开发**，也不要忘记同步。

---

## 1. 这个软件到底做什么

洛雪音乐桌面版（lx-music-desktop）支持「自定义音源脚本」。官方只提供手动导入单个脚本的入口，音源多了以后非常难管理。本工具解决四件事：

1. **批量导入**：扫描文件夹里所有 `.js` 音源，解析元数据，一次性写入 `user_api.json`
2. **批量更新**：按音源名称匹配，同名覆盖（保留原 id），无同名则新增
3. **备份还原**：每次写操作前自动备份，可手动备份、一键还原、查看/删除
4. **订阅更新**：从 GitHub 仓库（Release 附件或仓库目录）拉取最新音源并自动导入

---

## 2. 数据格式（最容易踩坑的地方）

### 2.1 user_api.json 结构

```json
{ "userApis": [ { "id": "user_api_001_1730000000000", "name": "...", "description": "...",
                  "version": "...", "author": "...", "homepage": "...",
                  "allowShowUpdateAlert": true, "script": "gz_...." } ] }
```

- `id` 格式：`user_api_<3位序号>_<毫秒时间戳>`，由 `gen_api_id()` 生成，**更新时必须保留原 id**
- `script` 格式：`'gz_' + base64(zlib.deflate(utf8_bytes))`，见 `compress_script()` / `decompress_script()`
- 元数据来自脚本头部 `/* ... */` 注释块，字段 `@name/@description/@version/@author/@homepage`，见 `parse_script_meta()`
- **长度上限**（与官方 `src/main/modules/userApi/utils.ts` 一致）：name 24 / description 36 / author 56 / homepage 1024 / version 36，超长会被截断

### 2.2 订阅目录结构

```
<下载目录>/<owner>/<repo>/          ← 注意是两段路径！owner/repo
├── *.js                            ← 只有最新版本
└── history/<tag>/                  ← 历史版本归档
```

**踩坑记录**：`sub_of_path()` 曾用 `relpath().split(os.sep)[0]` 反查订阅，因为订阅名是两段路径而永远匹配失败。正确做法是遍历订阅、用 `_sub_download_dir(sub)` 的完整路径做前缀匹配并取最长者。

---

## 3. 代码架构

### 3.1 单文件内的分层

```
常量与工具函数（short / short_path / version_key / normalize_name / hex_rgb）
  ↓
编解码（decode_script_bytes / compress_script / decompress_script）
  ↓
路径与配置（tool_dir / config_dir / load_settings / save_settings / subscriptions）
  ↓
音源读写（load_user_api / save_user_api / parse_script_meta / scan_source_folder）
  ↓
GitHub（parse_repo_ref / fetch_latest_release / fetch_repo_files / repo_revision）
  ↓
压缩包（_safe_extract_zip / _try_zip_password / _extract_js_from_zip）
  ↓
下载器（find_idm_path / find_abdm_path / mirrored_url）
  ↓
导入核心（apply_imports）+ 备份（BackupManager）
  ↓
BaseApp（1598 行 / 106 方法）← 所有业务逻辑
  ├── CtkApp（873 行 / 42 方法）← 只做视图
  └── TtkApp（645 行 / 31 方法）← 只做视图
  ↓
run_selftest / main
```

### 3.2 关键设计约定（**改代码前必须遵守**）

1. **业务逻辑只写在 BaseApp**。CtkApp / TtkApp 只能放视图方法（`_build_*` / `_view_*`）。曾经两套 UI 各写一份业务逻辑，导致改一处漏一处（`report['added']` 的 bug 就是这样漏了两个流程）。
2. **视图钩子模式**：BaseApp 里定义 `_view_xxx()` 空实现或 `raise NotImplementedError`，子类实现。BaseApp 只调钩子，不碰控件。
3. **列表行用原生 `tk.Frame` + `tk.Label`，不用 CTkFrame**。CTk 控件有画布层，快速滚动会产生拖尾残影。
4. **滚动容器必须放进 `pack_propagate(False)/grid_propagate(False)` 的 `tk.Frame` 里**。CTkScrollbar 默认请求 200px 宽/高，会撑破布局把列表压成 1px。
5. **行高与字号统一**：`f_title 17 / f_card 14 / f_base 13 / f_bold 13 / f_small 12 / f_tiny 11 / f_btn 13 / f_log 12`。新加控件用现成字号，不要造新的。
6. **列表行只有两段**：左边名称，右边 "` · `" 拼接的次要信息（由 `_cand_meta_text / _imp_meta_text / _sub_meta_text` 生成）。不要把一个行拆成 5 个 Label。
7. **强制 DPI 缩放 1.0**：`ctk.deactivate_automatic_dpi_awareness()` + `set_widget_scaling(1.0)` + `set_window_scaling(1.0)`。用户机器 150% DPI，不锁死窗口会变成 1830x1200 超出屏幕。

---

## 4. 订阅更新流程（最复杂的部分，改动前必读）

### 4.1 两条来源

| 来源 | `sub['source']` | 版本标记 `last_tag` | 说明 |
|---|---|---|---|
| Release 附件 | `'release'`（默认） | `release['tag_name']` | 下载 `.js` / `.zip` 附件 |
| 仓库目录 | `'repo'` | 目录最后一次提交的短 sha | 递归读取目录下 `.js`，跳过隐藏目录与 node_modules |

### 4.2 统一入口

```python
_fetch_sub_update(sub) -> (kind, tag, subdir, items)
# kind: 'skip' 已最新 / 'noasset' 无音源 / 'new' 有新版本
# 该函数在**后台线程**执行，只负责"检查 + 下载"，不碰界面、不弹窗
```

### 4.3 线程边界（**极重要**）

```
后台线程：检查更新 + 下载文件         ← 不能弹任何对话框
主线程  ：解压（可能弹密码框）+ 解析 + 写 user_api + 刷新界面
```

原因：加密 zip 需要弹密码输入框，在后台线程弹窗会崩。所以必须拆成 `_download_asset_file`（线程）和 `_extract_asset_main`（主线程）。

### 4.4 版本归档语义

```python
_archive_previous(subdir, tag, keep=True)
# keep=True  → 把根目录内容**移动**到 history/<tag>/（不是复制！）
# keep=False → 直接删除
# 目的：根目录永远只有最新版本，解决"新旧音源混杂、列表臃肿"
```

**历史 bug**：早期实现是 `copy2`/`copytree` 只复制不删除，导致根目录同时存在新旧两套音源，用户看到重复条目。改为移动语义后解决。

---

## 5. 下载器抽象

```python
_download_url_to(url, target) -> 'builtin' | 'idm' | 'abdm'
# 按 settings['downloader'] 决定：
#   'builtin' → 只用内置 urllib
#   'idm'     → 只用 IDM
#   'abdm'    → 只用 ABDM
#   'auto'    → 依次尝试 IDM → ABDM → 内置，任一成功即返回
```

- **IDM**：`IDMan.exe /d <url> /p <dir> /f <name> /n /s`，轮询等文件出现
- **ABDM**（AB Download Manager）：
  - 可执行文件是 **`ABDownloadManagerCli.exe`**（不是主程序 `ABDownloadManager.exe`，后者只接受 `gui run`）
  - CLI 语法：`download add http --link=<url> --folder=<dir> --name=<file> --start`（**等号形式**，目录要用正斜杠）
  - 本地 REST 服务：`POST http://127.0.0.1:15151/start-headless-download`，body `{"downloadSource":{"link":...},"folder":...}`
  - **实测结论**：该版本 ABDM 对 REST 返回 200 但任务不入队，CLI 也静默失败。因此**必须保留内置下载兜底**，不能只依赖 ABDM
  - 设置页有「测试 ABDM」按钮做服务探活（`GET /queues`）

---

## 6. 已知问题与待办

### 6.1 已修复（不要再引入）

- ✅ `report['added']` 是一元组 `(s,)`，三处日志循环曾写成 `for s in report['added']: s.name` → `AttributeError: 'tuple' object has no attribute 'name'` → 异常发生在 `sub['last_tag'] = tag` **之前**，导致版本标记永远不保存
- ✅ 压缩包内无 `.js` 时曾静默"成功"并误标已更新 → 现抛错并保留压缩包
- ✅ 清空备份目录输入框想恢复默认曾报"迁移失败" → 现空路径映射到默认目录
- ✅ IDM 失效曾不回退内置 → 现 `FileNotFoundError` 时置空 `idm_path` 并回退
- ✅ ttk 镜像预设 `configure(fg=...)` 崩 → 现 try/except 兼容
- ✅ 同一压缩包内同名音源多版本互相覆盖导致版本"倒退"（`v9.3 → v4.1`）→ 现按 `version_key()` 只保留最高版本

### 6.2 待办（按优先级）

**P0 —— 无**
（v1.1.1 后主流程未见阻塞问题）

**P1 —— 值得做**
1. **ABDM 真机验证**：等用户开启 ABDM「设置 → 集成」后，实测 REST/CLI 是否能真正落盘。若确认该版本不支持，考虑改走它写注册表/配置文件的间接方式，或明确在界面上降级提示
2. **进度反馈**：一键更新多个订阅时，目前只有文字日志，没有进度条。订阅多时用户不知道还要等多久
3. **失败重试**：网络抖动导致某订阅下载失败后，现在只能整体重来。可加"只重试失败的"

**P2 —— 体验优化**
4. **列表行右键菜单**已经做了（历史版本切换/详情/删除），但菜单项在有/无历史版本时的禁用态还可以更清楚
5. **搜索过滤**只匹配名称/作者/路径，可考虑加版本号
6. **备份列表**可以显示差量信息（这个备份比当前多了/少了几个音源）

**P3 —— 工程债**
7. BaseApp 已 1598 行 / 106 方法，可以按关注点拆成 Mixin（备份 / 订阅 / 设置 / 导入），但要小心 MRO
8. `_extract_js_from_zip` 现在只有自检在用，可以删或合并进 `_extract_asset_main`

---

## 7. 验收标准（每个改动必须全过）

```bash
# 1. 编译
python -m py_compile LXmusic一键导入和更新.py

# 2. 完整自检（核心逻辑 / 订阅逻辑 / CTk 界面 / ttk 界面 四段全绿）
python LXmusic一键导入和更新.py --selftest

# 3. 强制 ttk 界面自检
python LXmusic一键导入和更新.py --selftest --force-ttk
```

**行为级验证的固定套路**（自检覆盖不到的部分必须写临时脚本验证）：

```python
import importlib.util, tempfile, os
spec = importlib.util.spec_from_file_location('lxtool', r'<源码路径>')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
tmp = tempfile.mkdtemp()
# 补丁必须打在**模块对象**上，不能打 globals()
m.settings_path = lambda: os.path.join(tmp, 'settings.json')
m.subscriptions_path = lambda: os.path.join(tmp, 'subscriptions.json')
m.config_dir = lambda: os.path.join(tmp, 'cfg')
app = m.CtkApp(user_api_path=..., backup_dir=..., auto_confirm=True, hidden=True)
```

> **血泪教训**：`python -c` 里写 `globals()['settings_path'] = ...` 打的是 `__main__` 的全局，不是模块的！曾因此污染真实配置、把测试数据写进 `Default Project/config/settings.json`，后续所有测试都读到脏数据。

---

## 8. 打包发布

```powershell
# 生成图标
python -c "from PIL import Image, ImageDraw; img=Image.new('RGBA',(256,256),(0,0,0,0)); d=ImageDraw.Draw(img); d.rounded_rectangle([8,8,248,248],radius=56,fill=(217,119,87,255)); d.polygon([(96,72),(96,184),(192,128)],fill=(255,250,245,255)); img.save('C:/Users/28381/AppData/Local/Temp/lx_icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"

# 打包
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --icon 'C:/Users/28381/AppData/Local/Temp/lx_icon.ico' `
  --collect-all customtkinter `
  --name 'LXmusic一键导入和更新' 'LXmusic一键导入和更新.py'

# 【必须】修复完整性级别（否则用户双击报 Could not create temporary directory!）
icacls 'dist' /setintegritylevel Medium /T /C
```

**完整性级别陷阱（真实踩过）**：在受限沙箱里构建时，产物会被打上 `Mandatory Label\Low Mandatory Level`。低完整性进程无权往 `%TEMP%`（中完整性）写东西，单文件 exe 解压自己时就会失败，用户必须"以管理员身份运行"才行。构建后**一定要** `icacls /setintegritylevel Medium`，并`icacls <exe> | Select-String Mandatory` 复查。从 GitHub Release 下载的 exe 不受影响（下载会重建文件）。

---

## 9. 用户环境与偏好（不要违反）

- 用户是**中文交流**，所有界面文案、日志、提交信息都用中文
- 机器 150% DPI，屏幕 1707x1067，窗口必须锁死在 1220x800 左右
- 用户实际使用的程序在 `C:\Users\28381\Desktop\LX订阅\`（不是 Default Project）
- 用户的订阅：`guoyue2010/lxmusic-`（Release 来源，附件是 zip）
- **不要替用户改 README 里的免责声明/AI 声明**，那是用户自己写的
- 用户曾经因为"没数字签名"和"要管理员才能运行"困惑过，回答时要解释清楚这是**构建环境导致**，不是软件本身问题
- 网络：GitHub 直连经常超时，push 时加 `git -c http.lowSpeedLimit=2000 -c http.lowSpeedTime=20` 避免卡 5 分钟

---

## 10. 提交规范

```
<类型>: <一句话>
                        ← 空行
<正文：为什么改、怎么改、影响范围>
```

类型：`feat` 新功能 / `fix` 修 bug / `refactor` 重构 / `docs` 文档 / `chore` 杂务 / `perf` 性能

每次提交前必须：编译通过 → 自检全绿 → 行为验证 → 同步到仓库副本 → `git add -A` → commit → push。

---

## 11. 给接手者的第一句话

**先读第 3.2 节的设计约定和第 4.3 节的线程边界，再看代码。** 这两处违反一次就会引入难查的 bug。

改任何跟订阅相关的代码前，先读第 4 节全节。改任何跟打包相关的，先读第 8 节。
