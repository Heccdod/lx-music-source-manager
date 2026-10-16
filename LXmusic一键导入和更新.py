# -*- coding: utf-8 -*-
r"""
LX Music 音源一键导入 / 更新工具
=================================
针对洛雪音乐桌面版（lx-music-desktop）的自定义音源批量管理工具。

功能
----
1. 自动定位 C:\Users\<用户>\AppData\Roaming\lx-music-desktop\LxDatas\user_api.json
   （找不到时可点击「重新定位」手动选择）
2. 选择音源文件夹：自动遍历所有子文件夹，识别其中的 .js 音源脚本，并解析
   脚本头部的元数据注释（@name / @description / @version / @author / @homepage）
3. 待导入列表：勾选 / 多选 / 全选 / 移除（仅移出名单，不删除磁盘文件）/ 搜索过滤
4. 两种导入模式：
   - 导入模式：直接追加新增（与官方导入行为一致，内容完全相同自动跳过）
   - 更新模式：自动识别音源名称与版本，同名音源覆盖更新（保留 id），无同名则普通导入
5. 一键全部导入 / 更新
6. 备份管理：手动生成备份、一键还原备份、查看 / 删除 / 清空备份；所有写操作前自动备份
7. 已导入音源查看：列表展示 + 详情查看，支持删除所选 / 一键清除全部
8. GitHub 订阅：添加仓库订阅，一键检查并下载最新 Release 音源，自动以更新模式导入
   - 解压后自动删除原压缩包；支持加密压缩包（弹窗输入密码，会话内自动记住）
9. 镜像切换与 IDM：支持 GitHub 镜像前缀加速下载（国内网络友好）；检测到 IDM 时自动调起 IDM 下载，可手动切换内置下载

实现说明
--------
- 只读写 user_api.json，操作无需管理员权限，程序不会申请提权。
- 与官方源码（src/main/modules/userApi/utils.ts）保持一致：
  脚本以 'gz_' + base64(zlib.deflate(utf8)) 压缩存储；元数据解析规则一致；
  新增音源 id 格式为 user_api_<3位随机数>_<毫秒时间戳>，allowShowUpdateAlert 为 true。
- 修改 user_api.json 后，需要重启 LX Music 桌面版才会生效。
- 界面优先使用 customtkinter（首次运行会自动尝试 pip 安装），
  安装失败时自动回退到内置 tkinter/ttk 界面。
- 支持窗口淡入、列表惯性平滑滚动、行高亮过渡等轻量动画。
- 可打包为独立 exe：pip install pyinstaller 后运行
  pyinstaller --onefile --windowed --name "LXmusic一键导入和更新" LXmusic一键导入和更新.py

用法
----
- 正常运行：  python LXmusic一键导入和更新.py
- 自检模式：  python LXmusic一键导入和更新.py --selftest        （不弹出窗口）
- 强制 ttk 界面：python LXmusic一键导入和更新.py --force-ttk
"""

import os
import sys
import re
import json
import time
import zlib
import base64
import shutil
import random
import io
import zipfile
import queue
import threading
import subprocess
import tempfile
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

__version__ = '1.0.0'

APP_TITLE = 'LX Music 音源一键导入 / 更新工具'
FONT_FAMILY = 'Microsoft YaHei UI'
MODE_ADD_LABEL = '导入模式（直接新增）'
MODE_UPDATE_LABEL = '更新模式（同名更新）'

# ---------------------------------------------------------------- 配色（深色主题）
PALETTE = dict(
    bg='#f4f1ea',          # 窗口背景：奶油米白（Claude 风格暖色调）
    card='#fdfcf8',        # 卡片：暖白
    card2='#f3e2cc',       # 选中行：暖陶土色，与卡片/悬停明显区分
    field='#efeae0',       # 输入框 / 列表底
    border='#e5dccb',
    hover='#ede3d2',
    accent='#d97757',      # 陶土橙（Claude 强调色）
    accent_hover='#c86b4c',
    green='#4d9d70',
    warn='#cf8a3a',
    danger='#c05a48',
    text='#262220',
    muted='#7a7164',
    faint='#a89d8b',
)
LOG_COLORS = {
    'title': '#262220',
    'info': PALETTE['muted'],
    'ok': PALETTE['green'],
    'update': PALETTE['accent'],
    'warn': PALETTE['warn'],
    'error': PALETTE['danger'],
}


class WebCheck(tk.Canvas):
    """网页风格复选框：小方框 + 对勾，支持悬停反馈与禁用态（替代系统 Checkbutton）。"""

    def __init__(self, master, variable=None, command=None, size=18, colors=None):
        self._size = size
        self._colors = colors or PALETTE
        self.var = variable if variable is not None else tk.BooleanVar(value=False)
        self._command = command
        self._hover = False
        self._enabled = True
        try:
            bg = master.cget('bg')
        except Exception:
            bg = PALETTE['card']
        super().__init__(master, width=size, height=size, bg=bg,
                         highlightthickness=0, bd=0, cursor='hand2')
        self.bind('<Button-1>', self._on_click)
        self.bind('<Enter>', lambda e: self._set_hover(True))
        self.bind('<Leave>', lambda e: self._set_hover(False))
        self.var.trace_add('write', lambda *a: self._draw())
        self._draw()

    def set_state(self, enabled):
        """启用 / 禁用（禁用时置灰且不可点击）。"""
        self._enabled = bool(enabled)
        self._hover = False
        self._draw()

    def _on_click(self, _e):
        if not self._enabled:
            return
        self.var.set(not self.var.get())
        if self._command:
            self._command()

    def _set_hover(self, h):
        if not self._enabled:
            h = False
        self._hover = h
        self._draw()

    def _draw(self):
        c = self
        c.delete('all')
        s = self._size
        if self.var.get():
            if self._enabled:
                fill = outline = self._colors['accent']
            else:
                fill = outline = self._colors['faint']
            c.create_rectangle(1.5, 1.5, s - 1.5, s - 1.5, fill=fill,
                               outline=outline, width=1)
            c.create_line(5, s / 2 + 0.5, s / 2 - 1, s - 5, s - 5, 5,
                          fill='#fffaf5', width=2, capstyle=tk.ROUND, joinstyle=tk.ROUND)
        else:
            if self._enabled:
                outline = self._colors['hover'] if self._hover else self._colors['faint']
            else:
                outline = self._colors['border']
            c.create_rectangle(1.5, 1.5, s - 1.5, s - 1.5, fill='', outline=outline, width=1)


def short(text, n):
    """文本截断（None 安全）。"""
    text = '' if text is None else str(text)
    return text if len(text) <= n else text[:n - 1] + '…'


def short_path(path, limit=52):
    """路径过长时中间省略，保留盘符与文件名。"""
    path = path or ''
    if len(path) <= limit:
        return path
    head_len = max(12, limit // 2 - 2)
    head = path[:head_len]
    tail = path[-(limit - head_len - 3):]
    return head + '...' + tail


def normalize_name(name):
    return (name or '').strip().casefold()


def hex_rgb(h):
    """'#rrggbb' -> (r, g, b)。"""
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def decode_script_bytes(data):
    """按多种编码尝试解码脚本字节，返回 (文本, 编码)。"""
    if data.startswith(b'\xff\xfe') or data.startswith(b'\xfe\xff'):
        try:
            return data.decode('utf-16'), 'utf-16'
        except UnicodeError:
            pass
    for enc in ('utf-8-sig', 'utf-8', 'gbk'):
        try:
            return data.decode(enc), enc
        except UnicodeError:
            continue
    return data.decode('latin-1'), 'latin-1'


def read_text_auto(path):
    """按多种编码尝试读取文本文件，返回 (文本, 编码)。"""
    with open(path, 'rb') as f:
        return decode_script_bytes(f.read())


def compress_script(raw):
    """与官方 deflateScript 一致：'gz_' + base64(zlib deflate)。"""
    return 'gz_' + base64.b64encode(zlib.compress(raw.encode('utf-8'))).decode('ascii')


def decompress_script(stored):
    """与官方 inflateScript 一致：gz_ 前缀走 zlib inflate，否则原样返回。"""
    if stored and stored.startswith('gz_'):
        return zlib.decompress(base64.b64decode(stored[3:])).decode('utf-8')
    return stored or ''


# ---------------------------------------------------------------- user_api.json 读写
def default_user_api_path():
    appdata = os.environ.get('APPDATA')
    if not appdata:
        return None
    return os.path.join(appdata, 'lx-music-desktop', 'LxDatas', 'user_api.json')


def default_backup_dir():
    base = os.path.join(config_dir(), 'backups')
    for cand in (base, os.path.join(os.environ.get('LOCALAPPDATA', base), 'LXMusicTool', 'backups')):
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, '.probe')
            with open(probe, 'w') as f:
                f.write('ok')
            os.remove(probe)
            return cand
        except Exception:
            continue
    return base


def default_download_dir():
    """默认订阅下载目录：系统下载目录下的 lxsubscribe。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders') as k:
            dl = winreg.QueryValueEx(k, '{374DE290-123F-4565-9164-39C4925E467B}')[0]
        if dl and os.path.isdir(dl):
            return os.path.join(dl, 'lxsubscribe')
    except Exception:
        pass
    home = os.path.expanduser('~')
    for cand in (os.path.join(home, 'Downloads'), os.path.join(home, '下载')):
        if os.path.isdir(cand):
            return os.path.join(cand, 'lxsubscribe')
    return os.path.join(config_dir(), 'downloads')


def effective_backup_dir(settings):
    return (settings.get('backup_dir') or '').strip() or os.path.join(config_dir(), 'backups')


def effective_download_dir(settings):
    return (settings.get('download_dir') or '').strip() or default_download_dir()


def load_user_api(path):
    """读取 user_api.json，兼容官方新格式 / 旧格式。返回 (entries, err, msg)。"""
    if not path or not os.path.isfile(path):
        return [], None, '文件不存在'
    try:
        text, _ = read_text_auto(path)
        data = json.loads(text)
    except Exception as e:
        return [], e, '解析失败'
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        raw = data.get('userApis') or data.get('userApi') or []
    else:
        return [], None, '格式异常'
    entries = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        e = dict(item)
        if 'script' not in e and 'rawScript' in e:
            e['script'] = e.pop('rawScript')
        e.setdefault('script', '')
        e.setdefault('allowShowUpdateAlert', False)
        entries.append(e)
    return entries, None, None


def save_user_api(path, entries):
    """按官方格式原子写入：{"userApis": [...]}，Tab 缩进，UTF-8 无转义。"""
    directory = os.path.dirname(path) or '.'
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(directory, '.user_api_tmp_{}_{}.tmp'.format(os.getpid(), int(time.time() * 1000)))
    try:
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            json.dump({'userApis': entries}, f, ensure_ascii=False, indent='\t')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def gen_api_id(existing_ids):
    """生成与官方一致的 id：user_api_<3位随机>_<毫秒时间戳>（确保唯一）。"""
    while True:
        eid = 'user_api_{:03d}_{}'.format(random.randint(0, 999), int(time.time() * 1000))
        if eid not in existing_ids:
            return eid


# ---------------------------------------------------------------- 音源脚本解析
INFO_LIMITS = {'name': 24, 'description': 36, 'author': 56, 'homepage': 1024, 'version': 36}
_BLOCK_RE = re.compile(r'/\*[\s\S]+?\*/')
_META_RE = re.compile(r'^\s?\*\s?@(\w+)\s(.+)$')


def parse_script_meta(text, fallback_name=''):
    """解析脚本头部注释块中的元数据，规则与官方 parseScriptInfo 一致。"""
    info = {k: '' for k in INFO_LIMITS}
    m = _BLOCK_RE.match(text)
    if m:
        for line in m.group(0).splitlines():
            r = _META_RE.match(line)
            if r and r.group(1) in INFO_LIMITS:
                info[r.group(1)] = r.group(2).strip()
    for k, lim in INFO_LIMITS.items():
        if info[k] and len(info[k]) > lim:
            info[k] = info[k][:lim] + '...'
    if not info['name']:
        info['name'] = fallback_name or 'user_api_{}'.format(time.strftime('%Y-%m-%d %H:%M:%S'))
    if not info['version']:
        info['version'] = '1.0.0'
    return info


class SourceScript:
    __slots__ = ('path', 'rel_path', 'raw', 'name', 'version', 'description',
                 'author', 'homepage', 'encoding', 'meta_missing')

    def __init__(self, path, rel_path, raw, meta, encoding, meta_missing):
        self.path = path
        self.rel_path = rel_path
        self.raw = raw
        self.name = meta['name']
        self.version = meta['version']
        self.description = meta['description']
        self.author = meta['author']
        self.homepage = meta['homepage']
        self.encoding = encoding
        self.meta_missing = meta_missing


def scan_source_folder(folder):
    """遍历文件夹及所有子文件夹，识别全部 .js 音源脚本。"""
    found = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'history')]
        for fn in sorted(files):
            if fn.lower().endswith('.js'):
                found.append(os.path.join(root, fn))
    sources = []
    for full in found:
        rel = os.path.relpath(full, folder)
        text, enc = read_text_auto(full)
        meta = parse_script_meta(text, fallback_name=os.path.splitext(os.path.basename(full))[0])
        meta_missing = _BLOCK_RE.match(text) is None
        sources.append(SourceScript(full, rel, text, meta, enc, meta_missing))
    return sources


# ---------------------------------------------------------------- GitHub Release 订阅
GITHUB_API = 'https://api.github.com'
_GITHUB_HEADERS = {'User-Agent': 'lx-music-source-manager', 'Accept': 'application/vnd.github+json'}


def parse_repo_ref(text):
    """把 'owner/repo' 或完整仓库链接解析成 (owner, repo)。"""
    text = (text or '').strip()
    text = re.sub(r'^https?://[^/]+/', '', text)
    parts = [p for p in text.split('/') if p]
    if len(parts) < 2:
        raise ValueError('无法识别的 GitHub 仓库，请使用 owner/repo 或完整仓库链接')
    return parts[0], parts[1]


def _gh_get(url, timeout=20):
    req = urllib.request.Request(mirrored_url(url), headers=_GITHUB_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def fetch_latest_release(owner, repo, timeout=20):
    """获取仓库最新 Release（GitHub 官方 API，无需登录，匿名限额 60 次/小时）。"""
    try:
        return _gh_get('{}/repos/{}/{}/releases/latest'.format(GITHUB_API, owner, repo), timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError('仓库不存在，或尚未发布过 Release')
        raise ConnectionError('GitHub API 返回 HTTP {}'.format(e.code))
    except urllib.error.URLError as e:
        raise ConnectionError('网络错误：{}'.format(e.reason))


def download_bytes(url, timeout=30):
    """下载 Release 附件（自动跟随跳转；设置了镜像时走镜像前缀）。"""
    req = urllib.request.Request(mirrored_url(url), headers=_GITHUB_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def source_assets_of(release):
    """筛出 Release 附件中可能包含音源脚本的（.js 或 .zip）。"""
    out = []
    for a in release.get('assets') or []:
        if a.get('name', '').lower().endswith(('.js', '.zip')):
            out.append(a)
    return out


def fetch_repo_meta(repo, timeout=20):
    """读取仓库信息（用于拿默认分支）。"""
    owner, name = parse_repo_ref(repo)
    try:
        return _gh_get('{}/repos/{}/{}'.format(GITHUB_API, owner, name), timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError('仓库不存在或不可访问（私有仓库暂不支持）')
        raise ConnectionError('GitHub API 返回 HTTP {}'.format(e.code))
    except urllib.error.URLError as e:
        raise ConnectionError('网络错误：{}'.format(e.reason))


def fetch_repo_files(repo, subpath='', branch='', timeout=20, max_dirs=40):
    """列出仓库指定目录下的全部 .js 文件（递归，跳过隐藏目录与 node_modules）。
    返回 (files, ref)；files 每项含 path / name / size / download_url / _ref。"""
    owner, name = parse_repo_ref(repo)
    ref = (branch or '').strip()
    if not ref:
        ref = (fetch_repo_meta(repo, timeout).get('default_branch') or 'main')
    out = []
    stack = [(subpath or '').strip('/')]
    seen = 0
    while stack and seen < max_dirs:
        p = stack.pop()
        seen += 1
        url = '{}/repos/{}/{}/contents/{}?ref={}'.format(
            GITHUB_API, owner, name, urllib.parse.quote(p), urllib.parse.quote(ref))
        try:
            items = _gh_get(url, timeout)
        except urllib.error.HTTPError as e:
            if e.code == 404 and not p:
                raise ValueError('仓库目录不存在：{}'.format(subpath or '/'))
            continue
        except urllib.error.URLError as e:
            raise ConnectionError('网络错误：{}'.format(e.reason))
        if not isinstance(items, list):
            continue
        for it in items:
            t = it.get('type')
            if t == 'dir':
                dn = it.get('name', '')
                if dn.startswith('.') or dn == 'node_modules':
                    continue
                stack.append(it.get('path', ''))
            elif t == 'file' and it.get('name', '').lower().endswith('.js'):
                out.append({'path': it.get('path', ''), 'name': it.get('name', ''),
                            'size': it.get('size', 0), 'download_url': it.get('download_url', ''),
                            '_ref': ref})
    out.sort(key=lambda x: x['path'])
    return out, ref


def repo_revision(repo, subpath='', branch='', timeout=20):
    """取该目录最后一次提交的短 sha 与时间，作为「版本标记」。"""
    owner, name = parse_repo_ref(repo)
    url = '{}/repos/{}/{}/commits?per_page=1'.format(GITHUB_API, owner, name)
    if subpath:
        url += '&path=' + urllib.parse.quote(subpath.strip('/'))
    if branch:
        url += '&sha=' + urllib.parse.quote(branch)
    try:
        data = _gh_get(url, timeout)
    except Exception:
        return '', ''
    if isinstance(data, list) and data:
        sha = (data[0].get('sha') or '')[:7]
        date = ((data[0].get('commit') or {}).get('committer') or {}).get('date', '')
        return sha, date
    return '', ''


def _safe_extract_zip(zip_path, dest, password=None):
    """安全解压 zip 到目标目录（拦截路径穿越；支持密码；失败时清理半截文件）。"""
    base = os.path.normcase(os.path.abspath(dest)) + os.sep
    written = []
    with zipfile.ZipFile(zip_path) as zf:
        try:
            for info in zf.infolist():
                name = info.filename.replace('\\\\', '/')
                if name.startswith('/') or '..' in name.split('/'):
                    continue
                target = os.path.normcase(os.path.abspath(os.path.join(dest, name)))
                if not target.startswith(base):
                    continue
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    written.append(target)
                    with open(target, 'wb') as f:
                        f.write(zf.read(info, pwd=password))
        except Exception:
            for p in written:
                try:
                    os.remove(p)
                except OSError:
                    pass
            raise


_ZIP_PASSWORDS = {}


def _try_zip_password(zip_path, dest, pwd):
    """按多种常见编码尝试 zip 解压密码（windows 压缩包常用 gbk/cp437）。"""
    if not pwd:
        _safe_extract_zip(zip_path, dest, None)
        return
    first_err = None
    for enc in ('utf-8', 'gbk', 'cp437'):
        try:
            _safe_extract_zip(zip_path, dest, pwd.encode(enc))
            return
        except RuntimeError as e:
            first_err = first_err or e
            continue
    raise RuntimeError(first_err or '密码错误')


def _extract_js_from_zip(data, cap=20 * 1024 * 1024):
    """从 zip 内存数据中提取所有 .js 文件，返回 [(文件名, bytes)]。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        raise ValueError('附件不是有效的 zip 文件')
    out = []
    total = 0
    for info in zf.infolist():
        if info.is_dir() or not info.filename.lower().endswith('.js'):
            continue
        if info.file_size > cap:
            continue
        total += info.file_size
        if total > cap:
            raise ValueError('zip 解压内容过大，已中止')
        out.append((info.filename, zf.read(info)))
    if not out:
        raise ValueError('zip 内没有找到 .js 音源文件')
    return out


def tool_dir():
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def config_dir():
    """配置文件夹：所有配置/日志/备份集中存放，避免散落在 exe 旁边。"""
    d = os.path.join(tool_dir(), 'config')
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def subscriptions_path():
    return os.path.join(config_dir(), 'subscriptions.json')


def settings_path():
    return os.path.join(config_dir(), 'settings.json')


def logs_path():
    return os.path.join(config_dir(), 'logs', 'app.log')


DEFAULT_SETTINGS = {
    'mirror': '',
    'downloader': 'auto',
    'abdm_path': '',
    'use_idm': True,
    'backup_enabled': True,
    'backup_dir': '',
    'download_dir': '',
    'keep_history': True,
    'log_enabled': True,
    'log_window': True,
}

MIRROR_PLACEHOLDER = '例如 https://ghfast.top'


def load_subscriptions():
    """读取订阅状态文件（工具目录下的 subscriptions.json）。"""
    try:
        with open(subscriptions_path(), encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get('subscriptions', [])
        if isinstance(data, list):
            return [s for s in data if isinstance(s, dict)]
        return []
    except Exception:
        return []


def save_subscriptions(subs):
    p = subscriptions_path()
    os.makedirs(os.path.dirname(p) or '.', exist_ok=True)
    try:
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    data['subscriptions'] = subs
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def load_settings():
    """读取全部工具设置（config/settings.json）。"""
    data = {}
    try:
        with open(settings_path(), encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d, dict):
            data = d
    except Exception:
        pass
    out = dict(DEFAULT_SETTINGS)
    for k in DEFAULT_SETTINGS:
        if k in data and data[k] is not None:
            out[k] = data[k]
    # 旧版本只有 use_idm 开关，迁移到新的「下载方式」设置
    if 'downloader' not in data:
        if 'use_idm' in data:
            out['downloader'] = 'idm' if data.get('use_idm') else 'builtin'
        else:
            out['downloader'] = 'auto'
    return out


def save_settings(settings):
    p = settings_path()
    os.makedirs(os.path.dirname(p) or '.', exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


# ---------------------------------------------------------------- 镜像前缀与 IDM
_MIRROR = ''


def set_mirror(m):
    """设置镜像前缀（如 ghfast.top），空值表示直连；自动补 https:// 并去掉尾部斜杠。"""
    global _MIRROR
    m = (m or '').strip().rstrip('/')
    if m and not m.startswith(('http://', 'https://')):
        m = 'https://' + m
    _MIRROR = m


def get_mirror():
    return _MIRROR


def mirrored_url(url):
    """给原始 URL 加镜像前缀（ghproxy 系格式：镜像/https://原地址）。"""
    if _MIRROR:
        return _MIRROR + '/' + url
    return url


def find_idm_path():
    """探测 IDM（Internet Download Manager）的 IDMan.exe 路径，未安装返回 None（结果缓存）。"""
    if find_idm_path._cached is not None:
        return find_idm_path._cached
    found = None
    try:
        import winreg
        for key in (r'SOFTWARE\Internet Download Manager', r'SOFTWARE\WOW6432Node\Internet Download Manager'):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
                    d = winreg.QueryValueEx(k, 'InstallDir')[0]
                p = os.path.join(d, 'IDMan.exe')
                if os.path.isfile(p):
                    found = p
                    break
            except OSError:
                continue
    except Exception:
        pass
    if not found:
        for base in (os.environ.get('ProgramFiles(x86)', ''), os.environ.get('ProgramFiles', '')):
            p = os.path.join(base, 'Internet Download Manager', 'IDMan.exe')
            if os.path.isfile(p):
                found = p
                break
    if not found:
        try:
            out = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 '(Get-Process IDMan -ErrorAction SilentlyContinue | Select-Object -First 1).Path'],
                capture_output=True, text=True, timeout=10)
            p = (out.stdout or '').strip()
            if p and os.path.isfile(p):
                found = p
        except Exception:
            pass
    find_idm_path._cached = found
    return found


find_idm_path._cached = None


def find_abdm_path():
    """探测 AB Download Manager（ABDM）可执行文件，未安装返回 None（结果缓存）。
    依次尝试：PATH 命令 → 注册表安装信息 → 常见安装目录 → 正在运行的进程。"""
    if find_abdm_path._cached is not None:
        return find_abdm_path._cached
    found = None
    # 优先命令行版本：只有 ABDownloadManagerCli.exe 才能接收 download 子命令
    names = ('ABDownloadManagerCli.exe', 'ABDownloadManager.exe',
             'ab-download-manager.exe', 'abdm.exe', 'AB Download Manager.exe')
    for exe in ('abdm', 'ABDownloadManagerCli', 'ab-download-manager', 'ABDownloadManager'):
        try:
            p = shutil.which(exe)
        except Exception:
            p = None
        if p and os.path.isfile(p):
            found = p
            break
    if not found:
        try:
            import winreg
            roots = [
                (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'),
            ]
            for root, sub in roots:
                try:
                    with winreg.OpenKey(root, sub) as k:
                        count = winreg.QueryInfoKey(k)[0]
                except OSError:
                    continue
                for i in range(count):
                    try:
                        with winreg.OpenKey(k, winreg.EnumKey(k, i)) as sk:
                            try:
                                dn = str(winreg.QueryValueEx(sk, 'DisplayName')[0]).lower()
                            except OSError:
                                continue
                            if 'ab download manager' not in dn:
                                continue
                            for val in ('InstallLocation', 'DisplayIcon'):
                                try:
                                    v = str(winreg.QueryValueEx(sk, val)[0]).strip('"').split(',')[0].strip()
                                except OSError:
                                    continue
                                cand = v if v.lower().endswith('.exe') else os.path.join(v, 'ABDownloadManagerCli.exe')
                                if os.path.isfile(cand):
                                    found = cand
                                    break
                    except OSError:
                        continue
                    if found:
                        break
                if found:
                    break
        except Exception:
            pass
    if not found:
        bases = []
        for env in ('LOCALAPPDATA', 'ProgramFiles', 'ProgramFiles(x86)'):
            b = os.environ.get(env)
            if b:
                bases.append(b)
                bases.append(os.path.join(b, 'Programs'))
        for base in bases:
            for sub in ('AB Download Manager', 'ab-download-manager', 'ABDownloadManager'):
                for n in names:
                    p = os.path.join(base, sub, n)
                    if os.path.isfile(p):
                        found = p
                        break
                if found:
                    break
            if found:
                break
    if not found:
        try:
            out = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 "Get-Process | Where-Object { $_.ProcessName -like '*ab*download*' } | "
                 "Select-Object -First 1 -ExpandProperty Path"],
                capture_output=True, text=True, timeout=12)
            for line in (out.stdout or '').splitlines():
                line = line.strip()
                if line and os.path.isfile(line):
                    found = line
                    break
        except Exception:
            pass
    find_abdm_path._cached = found
    return found


find_abdm_path._cached = None


def apply_imports(entries, sources, mode):
    """
    核心导入逻辑（entries 原地修改，调用方负责保存）。
    mode: 'add' 直接新增；'update' 同名更新、无同名则新增。
    返回 {'added': [(s,)], 'updated': [(s, old_v, new_v)], 'skipped': [(s, 原因)], 'errors': [(s, 异常)]}
    """
    report = {'added': [], 'updated': [], 'skipped': [], 'errors': []}
    existing_ids = {e.get('id') for e in entries if e.get('id')}
    existing_scripts = {e.get('script') or '' for e in entries}
    for s in sources:
        try:
            comp = compress_script(s.raw)
            same = []
            if mode == 'update':
                key = normalize_name(s.name)
                same = [e for e in entries if normalize_name(e.get('name', '')) == key]
            if same:
                e = same[0]
                if (e.get('script') or '') == comp:
                    report['skipped'].append((s, '内容未变化，跳过'))
                    continue
                old_v = e.get('version', '?')
                e['name'] = s.name
                e['description'] = s.description
                e['version'] = s.version
                e['author'] = s.author
                e['homepage'] = s.homepage
                e['script'] = comp
                existing_scripts.add(comp)
                report['updated'].append((s, old_v, s.version))
                continue
            if comp in existing_scripts:
                report['skipped'].append((s, '与已有音源内容完全相同'))
                continue
            eid = gen_api_id(existing_ids)
            existing_ids.add(eid)
            entries.append({
                'id': eid,
                'name': s.name,
                'description': s.description,
                'version': s.version,
                'author': s.author,
                'homepage': s.homepage,
                'allowShowUpdateAlert': True,
                'script': comp,
            })
            existing_scripts.add(comp)
            report['added'].append((s,))
        except Exception as e:
            report['errors'].append((s, str(e)))
    return report


# ---------------------------------------------------------------- 备份管理
class BackupManager:
    def __init__(self, directory):
        self.directory = directory
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception:
            pass

    def create(self, src_path, reason='manual'):
        if not src_path or not os.path.isfile(src_path):
            raise FileNotFoundError('源文件不存在：{}'.format(src_path))
        os.makedirs(self.directory, exist_ok=True)
        ts = time.strftime('%Y%m%d_%H%M%S')
        name = 'user_api_{}_{}.json'.format(reason, ts)
        target = os.path.join(self.directory, name)
        n = 2
        while os.path.exists(target):
            target = os.path.join(self.directory, 'user_api_{}_{}_{}.json'.format(reason, ts, n))
            n += 1
        shutil.copy2(src_path, target)
        return target

    def list_files(self):
        files = []
        try:
            for fn in os.listdir(self.directory):
                if not fn.lower().endswith('.json'):
                    continue
                p = os.path.join(self.directory, fn)
                try:
                    st = os.stat(p)
                    files.append({
                        'name': fn, 'path': p, 'size': st.st_size,
                        'mtime': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime)),
                    })
                except OSError:
                    continue
        except OSError:
            pass
        files.sort(key=lambda f: f['name'], reverse=True)
        return files

    def delete(self, names):
        n = 0
        for name in names:
            try:
                p = os.path.join(self.directory, name)
                if os.path.isfile(p):
                    os.remove(p)
                    n += 1
            except OSError:
                pass
        return n

    def clear(self):
        return self.delete([f['name'] for f in self.list_files()])


# ---------------------------------------------------------------- 业务逻辑基类（与 UI 无关）
class BaseApp:
    # 订阅下载方式（界面下拉用的中文标签）
    DL_LABELS = {'auto': '自动', 'builtin': '内置', 'idm': 'IDM', 'abdm': 'ABDM'}

    def __init__(self, user_api_path=None, backup_dir=None, auto_confirm=False):
        self.auto_confirm = auto_confirm
        self.settings = load_settings()
        set_mirror(self.settings['mirror'])
        self.use_idm = bool(self.settings['use_idm'])
        self.idm_path = find_idm_path()
        self.abdm_path = self.settings.get('abdm_path') or find_abdm_path()
        self.user_api_path = user_api_path if user_api_path is not None else default_user_api_path()
        self.backup_dir = backup_dir if backup_dir is not None else effective_backup_dir(self.settings)
        self.backups = BackupManager(self.backup_dir)
        self.entries = []
        self.candidates = []
        self.checked_candidates = set()
        self.checked_imported = set()
        self.checked_backups = set()
        self.candidate_filter = ''
        self.import_mode = 'add'
        self.last_folder = os.path.expanduser('~')
        self.subscriptions = load_subscriptions()
        self._current_sub = None
        self._settings_win = None
        self._load_data()
        self._view_refresh_backups()
        self._view_refresh_subscriptions()
        self._view_refresh_candidates()

    # ---------------- 日志 / 提示 ----------------
    def log(self, text, level='info'):
        line = '[{}] {}'.format(time.strftime('%H:%M:%S'), text)
        self._view_log(line, level)
        if self.settings.get('log_enabled', True):
            try:
                p = logs_path()
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, 'a', encoding='utf-8') as f:
                    f.write(time.strftime('[%Y-%m-%d %H:%M:%S] ') + text + '\n')
            except Exception:
                pass

    def _confirm(self, title, message, danger=False):
        if self.auto_confirm:
            return True
        return self._view_confirm(title, message, danger=danger)

    def _info(self, title, message):
        if self.auto_confirm:
            return
        self._view_info(title, message)

    # ---------------- 数据 ----------------
    def _load_data(self):
        self.log('LX Music 音源一键导入 / 更新工具  v{}'.format(__version__), 'title')
        if not self.user_api_path:
            self.log('未找到 LX Music 数据目录（APPDATA 不可用），请点击「重新定位」手动选择 user_api.json', 'error')
        else:
            self.log('数据文件：{}'.format(self.user_api_path), 'info')
        self.entries, err, msg = load_user_api(self.user_api_path or '')
        if err is not None:
            self.log('读取 user_api.json 失败：{}（{}）'.format(msg, err), 'error')
            self.entries = []
        elif not os.path.isfile(self.user_api_path or ''):
            self.log('未找到 user_api.json，将按空列表创建新文件', 'warn')
            self.entries = []
        else:
            n_bad = sum(1 for e in self.entries if not e.get('script'))
            tip = '（{} 个缺少脚本内容）'.format(n_bad) if n_bad else ''
            self.log('已加载 {} 个已导入音源{}'.format(len(self.entries), tip), 'ok')
        if self.path_label is not None:
            self.path_label.configure(text='数据文件：' + (short_path(self.user_api_path, 48) or '未定位'))
        self._view_refresh_imported()
        self._view_status()

    def _view_status(self):
        p = self.user_api_path
        if p and os.path.isfile(p):
            w = '可写' if os.access(p, os.W_OK) else '只读'
        elif p and os.path.isdir(os.path.dirname(p)):
            w = '目录可写' if os.access(os.path.dirname(p), os.W_OK) else '目录不可写'
        else:
            w = '未定位'
        self._view_set_status('数据文件：{}  [{}]    备份目录：{}    修改后需重启 LX Music 生效'.format(
            short_path(p, 46) or '(未定位)', w, short_path(self.backup_dir, 36)))

    def _auto_backup(self):
        if not self.settings.get('backup_enabled', True):
            return True
        try:
            p = self.backups.create(self.user_api_path, reason='auto')
            self.log('已自动备份：{}'.format(os.path.basename(p)), 'info')
            self._view_refresh_backups()
            return True
        except Exception as e:
            return self._confirm('自动备份失败', '备份失败：{}\n\n仍要继续操作吗？'.format(e), danger=True)

    def _save_entries(self, what='写入'):
        try:
            save_user_api(self.user_api_path, self.entries)
            return True
        except Exception as e:
            self.log('{} user_api.json 失败：{}（原文件未受影响）'.format(what, e), 'error')
            return False

    # ---------------- 候选音源 ----------------
    def _candidate_visible(self, i):
        s = self.candidates[i]
        if not self.candidate_filter:
            return True
        hay = '{} {} {} {} {}'.format(s.name, s.version, s.author, s.description, s.rel_path).lower()
        return self.candidate_filter in hay

    def _on_search(self):
        self.candidate_filter = (self.search_var.get() or '').strip().lower()
        self._view_refresh_candidates()

    def do_scan_folder(self, folder=None):
        if folder is None:
            folder = self._view_ask_folder()
            if not folder:
                return
        self.last_folder = folder
        try:
            sources = scan_source_folder(folder)
        except Exception as e:
            self.log('扫描文件夹失败：{}'.format(e), 'error')
            return
        existing = {os.path.normcase(os.path.abspath(s.path)) for s in self.candidates}
        added = 0
        skipped = 0
        for s in sources:
            key = os.path.normcase(os.path.abspath(s.path))
            if key in existing:
                skipped += 1
                continue
            self.candidates.append(s)
            existing.add(key)
            added += 1
        self.folder_label.configure(text=short('已选择：' + os.path.basename(os.path.abspath(folder)), 46))
        level = 'ok' if added else 'warn'
        self.log('扫描完成：共发现 {} 个 .js 音源，新增 {} 个，重复跳过 {} 个'.format(len(sources), added, skipped), level)
        no_meta = [s for s in sources if s.meta_missing]
        if no_meta:
            names = '、'.join(os.path.basename(s.path) for s in no_meta[:5])
            more = ' …' if len(no_meta) > 5 else ''
            self.log('警告：{} 个脚本缺少元数据注释，已按文件名命名：{}{}'.format(len(no_meta), names, more), 'warn')
        self._view_refresh_candidates()

    def do_select_all_candidates(self, select=True):
        visible = [i for i in range(len(self.candidates)) if self._candidate_visible(i)]
        if select:
            self.checked_candidates.update(visible)
        else:
            self.checked_candidates.difference_update(visible)
        self._view_refresh_candidates()

    def do_remove_candidates(self):
        idxs = sorted(i for i in self.checked_candidates if 0 <= i < len(self.candidates))
        if not idxs:
            self._info('提示', '请先勾选要移除的音源')
            return
        names = '、'.join(self.candidates[i].name for i in idxs[:5])
        for i in reversed(idxs):
            self.candidates.pop(i)
        self.checked_candidates = set()
        self.log('已从待导入名单移除 {} 个音源（磁盘文件未删除）：{}{}'.format(len(idxs), names, ' …' if len(idxs) > 5 else ''), 'info')
        self._view_refresh_candidates()

    def do_clear_candidates(self):
        n = len(self.candidates)
        if not n:
            self._info('提示', '待导入列表已为空')
            return
        if not self._confirm('确认清空待导入列表？', '将清空全部 {} 个待导入音源。\n\n注意：仅移出名单，不会删除磁盘上的文件。'.format(n)):
            return
        self.candidates = []
        self.checked_candidates = set()
        self.log('已清空待导入名单', 'info')
        self._view_refresh_candidates()

    # ---------------- 导入 / 更新 ----------------
    def _set_mode(self, value):
        self.import_mode = 'update' if str(value).startswith('更新') else 'add'
        self._update_action_buttons()
        self.log('导入模式切换为：{}'.format('更新模式（同名更新，无同名则新增）' if self.import_mode == 'update' else '导入模式（直接新增）'), 'info')

    def _update_action_buttons(self):
        k = len(self.checked_candidates)
        upd = self.import_mode == 'update'
        self.btn_import_sel.configure(text=('更新所选' if upd else '导入所选') + (' ({})'.format(k) if k else ''))
        self.btn_import_all.configure(text='一键全部更新' if upd else '一键全部导入')

    def do_import(self, all_selected=False):
        if not self.candidates:
            self._info('提示', '待导入列表为空，请先选择音源文件夹')
            return
        if all_selected:
            idxs = list(range(len(self.candidates)))
        else:
            idxs = sorted(i for i in self.checked_candidates if 0 <= i < len(self.candidates))
        if not idxs:
            self._info('提示', '请先在列表中勾选要导入的音源，或使用「一键全部导入」')
            return
        sources = [self.candidates[i] for i in idxs]
        upd = self.import_mode == 'update'
        mode_label = '更新模式（同名更新，无同名则新增）' if upd else '导入模式（直接新增）'
        preview = '\n'.join('  · {}  (v{})'.format(s.name, s.version) for s in sources[:6])
        if len(sources) > 6:
            preview += '\n  · … 等共 {} 个'.format(len(sources))
        action = '更新' if upd else '导入'
        if not self._confirm('确认{} {} 个音源？'.format(action, len(sources)),
                             '处理模式：{}\n\n{}\n\n操作前将自动备份 user_api.json。'.format(mode_label, preview)):
            return
        if not self._auto_backup():
            return
        report = apply_imports(self.entries, sources, self.import_mode)
        if not self._save_entries('写入 user_api.json'):
            return
        ok_ids = set()
        for s, old_v, new_v in report['updated']:
            self.log('更新：{}  v{} → v{}'.format(s.name, old_v, new_v), 'update')
            ok_ids.add(id(s))
        for s in report['added']:
            self.log('新增：{}  v{}'.format(s.name, s.version), 'ok')
            ok_ids.add(id(s))
        for s, reason in report['skipped']:
            self.log('跳过：{}（{}）'.format(s.name, reason), 'warn')
        for s, err in report['errors']:
            self.log('失败：{}：{}'.format(s.name, err), 'error')
        self.log('完成：新增 {} / 更新 {} / 跳过 {} / 失败 {}；修改已写入，重启 LX Music 后生效'.format(
            len(report['added']), len(report['updated']), len(report['skipped']), len(report['errors'])), 'title')
        for i in idxs:
            if id(self.candidates[i]) in ok_ids:
                self.checked_candidates.discard(i)
        self._view_refresh_candidates()
        self._view_refresh_imported()
        self._view_status()

    # ---------------- 已导入音源 ----------------
    def do_delete_imported(self):
        idxs = sorted(i for i in self.checked_imported if 0 <= i < len(self.entries))
        if not idxs:
            self._info('提示', '请先在已导入列表中勾选要删除的音源')
            return
        names = '、'.join(str(self.entries[i].get('name', '?')) for i in idxs[:5])
        if not self._confirm('确认删除所选音源？', '将删除 {} 个已导入音源：\n{}{}\n\n删除前将自动备份。'.format(
                len(idxs), names, ' …' if len(idxs) > 5 else '')):
            return
        if not self._auto_backup():
            return
        for i in reversed(idxs):
            self.entries.pop(i)
        if not self._save_entries('保存'):
            return
        self.checked_imported = set()
        self.log('已删除 {} 个已导入音源', 'ok')
        self._view_refresh_imported()
        self._view_status()

    def do_clear_imported(self):
        n = len(self.entries)
        if not n:
            self._info('提示', '当前没有已导入的音源')
            return
        if not self._confirm('确认一键清除全部？', '将清除 user_api.json 中的全部 {} 个音源。\n\n清除前将自动备份，此操作不可撤销！'.format(n), danger=True):
            return
        if not self._auto_backup():
            return
        self.entries = []
        if not self._save_entries('保存'):
            return
        self.checked_imported = set()
        self.log('已清除全部 {} 个已导入音源，重启 LX Music 后生效'.format(n), 'ok')
        self._view_refresh_imported()
        self._view_status()

    # ---------------- 备份 ----------------
    def do_backup(self):
        try:
            p = self.backups.create(self.user_api_path, reason='manual')
            self.log('已生成备份：{}'.format(os.path.basename(p)), 'ok')
            self._view_refresh_backups()
        except Exception as e:
            self.log('备份失败：{}'.format(e), 'error')

    def do_delete_backups(self):
        names = sorted(self.checked_backups)
        if not names:
            self._info('提示', '请先在备份列表中勾选要删除的备份')
            return
        if not self._confirm('确认删除所选备份？', '将删除 {} 个备份文件。'.format(len(names))):
            return
        n = self.backups.delete(names)
        self.checked_backups = set()
        self.log('已删除 {} 个备份文件'.format(n), 'ok')
        self._view_refresh_backups()

    def do_clear_backups(self):
        files = self.backups.list_files()
        if not files:
            self._info('提示', '当前没有备份文件')
            return
        if not self._confirm('确认清空所有备份？', '将删除全部 {} 个备份文件。'.format(len(files))):
            return
        n = self.backups.clear()
        self.checked_backups = set()
        self.log('已清空 {} 个备份文件'.format(n), 'ok')
        self._view_refresh_backups()

    def do_restore_backup(self):
        names = sorted(self.checked_backups)
        if not names:
            self._info('提示', '请先在备份列表中勾选要还原的备份')
            return
        if len(names) > 1:
            self._info('提示', '一次只能还原一个备份，请只勾选一个')
            return
        name = names[0]
        files = {f['name']: f['path'] for f in self.backups.list_files()}
        src = files.get(name)
        if not src or not os.path.isfile(src):
            self.log('备份文件不存在：{}'.format(name), 'error')
            return
        entries, err, msg = load_user_api(src)
        if err is not None:
            self.log('备份内容无法解析（{}），已取消还原'.format(msg), 'error')
            return
        if not self._confirm('确认还原备份？', '将用备份「{}」（内含 {} 个音源）覆盖当前 user_api.json。\n\n还原前会自动备份当前状态，此操作不可撤销！'.format(name, len(entries)), danger=True):
            return
        if not self._auto_backup():
            return
        try:
            shutil.copy2(src, self.user_api_path)
        except Exception as e:
            self.log('还原失败：{}'.format(e), 'error')
            return
        self.checked_backups = set()
        self._load_data()
        self._view_refresh_backups()
        self.log('已还原备份「{}」，重启 LX Music 后生效'.format(name), 'ok')

    # ---------------- GitHub 订阅 ----------------
    def _run_task(self, fn, on_done, busy_label='处理中…'):
        """后台线程执行 fn，完成后在主线程回调 on_done(ok, result_or_error)。"""
        self.log(busy_label, 'info')
        q = queue.Queue()
        threading.Thread(target=lambda: self._task_worker(fn, q), daemon=True).start()
        self._poll_task(q, on_done)

    def _task_worker(self, fn, q):
        try:
            q.put(('ok', fn()))
        except Exception as e:
            q.put(('err', str(e)))

    def _poll_task(self, q, on_done):
        try:
            item = q.get_nowait()
        except queue.Empty:
            try:
                self.root.after(150, lambda: self._poll_task(q, on_done))
            except Exception:
                pass
            return
        try:
            on_done(*item)
        except Exception as e:
            self.log('任务回调异常：{}'.format(e), 'error')

    def _view_subscription_form(self, repo_text=''):
        # 添加订阅表单：仓库 + 来源（Release 附件 / 仓库目录）+ 目录路径 + 分支
        C = self.C
        f_small = getattr(self, 'f_small', None)
        if not isinstance(f_small, tuple):
            f_small = (FONT_FAMILY, 10)
        f_bold = getattr(self, 'f_bold', None)
        if not isinstance(f_bold, tuple):
            f_bold = (FONT_FAMILY, 10, 'bold')
        dlg = tk.Toplevel(self.root)
        dlg.title('添加订阅')
        dlg.configure(bg=C['card'])
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        body = tk.Frame(dlg, bg=C['card'])
        body.pack(padx=20, pady=(16, 0), fill='both')
        body.grid_columnconfigure(0, weight=1)

        def lab(r, text, color=None):
            tk.Label(body, text=text, bg=C['card'], fg=color or C['muted'], font=f_small,
                     anchor='w').grid(row=r, column=0, sticky='w', pady=(9, 2))

        def entry(r, var, width=46):
            e = tk.Entry(body, textvariable=var, width=width, bg=C['field'], fg=C['text'],
                         relief='flat', highlightthickness=1, highlightbackground=C['border'],
                         highlightcolor=C['accent'], font=f_small, insertbackground=C['text'])
            e.grid(row=r, column=0, sticky='ew', ipady=5)
            return e

        var_repo = tk.StringVar(value=repo_text or '')
        var_path = tk.StringVar()
        var_branch = tk.StringVar()
        kind = tk.StringVar(value='release')
        lab(0, 'GitHub 仓库（owner/repo 或完整链接）')
        e_repo = entry(1, var_repo)
        lab(2, '来源')
        pick = tk.Frame(body, bg=C['card'])
        pick.grid(row=3, column=0, sticky='w')
        for val, txt in (('release', 'Release 附件（默认，读取最新 Release 的 .js / .zip）'),
                         ('repo', '仓库目录（音源直接放在仓库里，逐个读取 .js）')):
            tk.Radiobutton(pick, text=txt, value=val, variable=kind, bg=C['card'], fg=C['text'],
                           selectcolor=C['card2'], activebackground=C['card'],
                           activeforeground=C['text'], font=f_small, anchor='w',
                           highlightthickness=0, bd=0).pack(anchor='w')
        lab(4, '目录路径（仅仓库目录模式；留空 = 仓库根目录，如 js / sources）')
        entry(5, var_path)
        lab(6, '分支（留空 = 默认分支）')
        entry(7, var_branch)
        tk.Label(body, text='不确定就保持「Release 附件」：仓库把音源打包进 Release 时用它；\n'
                            '若音源直接放在仓库目录（如根目录 / js 目录）里，请选「仓库目录」。',
                 bg=C['card'], fg=C['faint'], font=f_small, justify='left', anchor='w').grid(
            row=8, column=0, sticky='w', pady=(10, 0))
        btns = tk.Frame(dlg, bg=C['card'])
        btns.pack(pady=(12, 16))
        result = {}

        def ok():
            result['repo'] = var_repo.get().strip()
            result['source'] = kind.get()
            result['path'] = var_path.get().strip()
            result['branch'] = var_branch.get().strip()
            dlg.destroy()

        tk.Button(btns, text='取消', width=10, bg=C['card'], fg=C['muted'], relief='flat',
                  activebackground=C['hover'], activeforeground=C['text'], font=f_small,
                  command=dlg.destroy).pack(side='left', padx=6)
        tk.Button(btns, text='添加', width=10, bg=C['accent'], fg='#fffaf5', relief='flat',
                  activebackground=C['accent_hover'], activeforeground='#fffaf5', font=f_bold,
                  command=ok).pack(side='left', padx=6)
        e_repo.bind('<Return>', lambda e: ok())
        try:
            dlg.update_idletasks()
            x = self.root.winfo_rootx() + max((self.root.winfo_width() - dlg.winfo_reqwidth()) // 2, 0)
            y = self.root.winfo_rooty() + max((self.root.winfo_height() - dlg.winfo_reqheight()) // 3, 0)
            dlg.geometry('+{}+{}'.format(x, y))
        except Exception:
            pass
        dlg.after(80, e_repo.focus_set)
        dlg.wait_window()
        return result or None

    def do_add_subscription(self, repo_ref=None):
        if repo_ref is not None:
            form = {'repo': repo_ref, 'source': 'release', 'path': '', 'branch': ''}
        else:
            form = self._view_subscription_form()
        if not form or not (form.get('repo') or '').strip():
            return
        try:
            owner, repo = parse_repo_ref(form['repo'])
        except ValueError as e:
            self._info('无法添加', str(e))
            return
        key = '{}/{}'.format(owner, repo)
        if any(s.get('repo') == key for s in self.subscriptions):
            self._info('提示', '该仓库已在订阅列表中')
            return
        src = form.get('source') or 'release'
        subpath = (form.get('path') or '').strip().strip('/')
        branch = (form.get('branch') or '').strip()

        def fetch():
            if src == 'repo':
                files, ref = fetch_repo_files(key, subpath, branch)
                rev, _date = repo_revision(key, subpath, branch)
                return {'kind': 'repo', 'files': files, 'ref': ref, 'rev': rev}
            return {'kind': 'release', 'rel': fetch_latest_release(owner, repo)}

        def done(ok, payload):
            if not ok:
                self._info('添加失败', '无法读取该仓库：\n\n{}'.format(payload))
                return
            if payload['kind'] == 'repo':
                files = payload['files']
                if not files:
                    self._info('添加失败', '该目录下没有找到 .js 音源文件{}'.format(
                        '（目录：{}）'.format(subpath) if subpath else '（仓库根目录）'))
                    return
                tag = payload.get('rev') or payload.get('ref') or ''
                sub = {'repo': key, 'name': key, 'last_tag': '', 'source': 'repo',
                       'path': subpath, 'branch': branch,
                       'added_at': time.strftime('%Y-%m-%d %H:%M:%S')}
                self.subscriptions.append(sub)
                save_subscriptions(self.subscriptions)
                self._view_refresh_subscriptions()
                self.log('已添加订阅：{}（仓库目录{}，找到 {} 个音源，最新提交 {}）'.format(
                    key, ' ' + subpath if subpath else ' 根目录', len(files), tag or '?'), 'ok')
                if self._confirm('立即下载并导入？', '是否立即下载「{}」目录下的 {} 个音源并导入？'.format(key, len(files))):
                    self.do_update_subscription(sub)
                return
            rel = payload['rel']
            assets = source_assets_of(rel)
            if not assets:
                self._info('添加失败', '最新版本「{}」的附件中没有 .js / .zip 音源。\n\n'
                                       '如果该仓库把音源直接放在目录里，请改用「仓库目录」来源。'.format(rel.get('tag_name', '?')))
                return
            sub = {'repo': key, 'name': key, 'last_tag': '', 'asset_names': [a['name'] for a in assets],
                   'source': 'release', 'path': '', 'branch': branch,
                   'added_at': time.strftime('%Y-%m-%d %H:%M:%S')}
            self.subscriptions.append(sub)
            save_subscriptions(self.subscriptions)
            self._view_refresh_subscriptions()
            self.log('已添加订阅：{}（最新 {}，附件 {} 个）'.format(key, rel.get('tag_name'), len(assets)), 'ok')
            if self._confirm('立即下载并导入？', '是否立即下载「{}」的最新版本并导入？\n\n当前最新版本：{}'.format(key, rel.get('tag_name'))):
                self.do_update_subscription(sub)

        tip = '正在读取 {} 的仓库目录…'.format(key) if src == 'repo' else '正在查询 {} 的最新 Release…'.format(key)
        self._run_task(fetch, done, tip)

    def do_check_subscriptions(self):
        if not self.subscriptions:
            self._info('提示', '尚未添加任何订阅，请先点「添加订阅」')
            return
        subs = list(self.subscriptions)

        def work():
            out = []
            for sub in subs:
                try:
                    rel = fetch_latest_release(*sub['repo'].split('/'))
                    out.append((sub, 'ok', rel.get('tag_name', '?')))
                except Exception as e:
                    out.append((sub, 'err', str(e)))
            return out

        def done(ok, payload):
            if not ok:
                self.log('检查订阅失败：{}'.format(payload), 'error')
                return
            for sub, kind, info in payload:
                if kind == 'err':
                    self.log('「{}」检查失败：{}'.format(sub['repo'], info), 'error')
                elif sub.get('last_tag') and info == sub.get('last_tag'):
                    self.log('「{}」已是最新：{}'.format(sub['repo'], info), 'ok')
                else:
                    self.log('「{}」发现新版本：最新 {}（本地已用 {}）'.format(sub['repo'], info, sub.get('last_tag') or '无'), 'update')

        self._run_task(work, done, '正在检查全部订阅…')

    def do_update_subscription(self, sub):
        def work():
            return self._fetch_sub_update(sub)

        def done(ok, payload):
            if not ok:
                self.log('「{}」更新失败：{}'.format(sub['repo'], payload), 'error')
                self._view_refresh_subscriptions()
                return
            kind, tag, subdir, items = payload
            if kind == 'skip':
                self.log('「{}」已是最新版本 {}，无需更新'.format(sub['repo'], tag), 'ok')
                self._view_refresh_subscriptions()
                return
            if kind == 'noasset':
                self.log('「{}」v{} 没有 .js / .zip 附件，跳过'.format(sub['repo'], tag), 'warn')
                return
            try:
                scripts = []
                for target, name in items:
                    scripts.extend(self._extract_asset_main(target, name,
                                                            'github:{}#{}'.format(sub['repo'], tag), subdir))
                if not self._auto_backup():
                    return
                report = apply_imports(self.entries, scripts, 'update')
                if not self._save_entries('写入 user_api.json'):
                    return
                for s, old_v, new_v in report['updated']:
                    self.log('更新：{}  v{} → v{}（来自 {}）'.format(s.name, old_v, new_v, sub['repo']), 'update')
                for s in report['added']:
                    self.log('新增：{}  v{}（来自 {}）'.format(s.name, s.version, sub['repo']), 'ok')
                for s, reason in report['skipped']:
                    self.log('跳过：{}（{}）'.format(s.name, reason), 'warn')
                for s, err in report['errors']:
                    self.log('失败：{}：{}'.format(s.name, err), 'error')
                sub['last_tag'] = tag
                save_subscriptions(self.subscriptions)
                # 更新后自动把该订阅的最新版本音源加载到「待导入音源」
                self._current_sub = sub.get('repo')
                loaded = self._load_sub_sources(sub, silent=True)
                self._view_refresh_subscriptions()
                self._view_refresh_imported()
                self._view_status()
                self.log('订阅「{}」处理完成（新增 {} / 更新 {} / 跳过 {}），待导入区已载入 {} 个最新音源，重启 LX Music 后生效'.format(
                    sub['repo'], len(report['added']), len(report['updated']), len(report['skipped']),
                    loaded[0] if loaded else 0), 'title')
            except Exception as e:
                self.log('「{}」下载/解析失败：{}'.format(sub['repo'], e), 'error')

        self._run_task(work, done, '正在更新订阅 {}…'.format(sub['repo']))

    def do_update_all_subscriptions(self):
        if not self.subscriptions:
            self._info('提示', '尚未添加任何订阅，请先点「添加订阅」')
            return
        subs = list(self.subscriptions)
        if not self._confirm('一键订阅更新？', '将对 {} 个订阅逐个检查最新 Release，发现新版本自动下载并以「更新模式」导入。'.format(len(subs))):
            return

        def work():
            out = []
            for sub in subs:
                try:
                    kind, tag, subdir, items = self._fetch_sub_update(sub)
                    if kind == 'skip':
                        out.append((sub, 'skip', tag))
                    elif kind == 'noasset':
                        out.append((sub, 'noasset', tag))
                    else:
                        out.append((sub, 'new', tag, subdir, items))
                except Exception as e:
                    out.append((sub, 'err', str(e)))
            return out

        def done(ok, payload):
            if not ok:
                self.log('一键订阅更新失败：{}'.format(payload), 'error')
                return
            has_new = any(item[1] == 'new' for item in payload)
            if has_new and not self._auto_backup():
                return
            for item in payload:
                sub, kind = item[0], item[1]
                if kind == 'skip':
                    self.log('「{}」已是最新 {}'.format(sub['repo'], item[2]), 'ok')
                elif kind == 'noasset':
                    self.log('「{}」v{} 没有 .js / .zip 附件，跳过'.format(sub['repo'], item[2]), 'warn')
                elif kind == 'err':
                    self.log('「{}」检查失败：{}'.format(sub['repo'], item[2]), 'error')
                else:
                    tag, subdir, items = item[2], item[3], item[4]
                    self.log('「{}」发现新版本 {}，正在导入…'.format(sub['repo'], tag), 'info')
                    try:
                        scripts = []
                        for target, name in items:
                            scripts.extend(self._extract_asset_main(target, name,
                                                                    'github:{}#{}'.format(sub['repo'], tag), subdir))
                    except Exception as e:
                        self.log('「{}」解压/解析失败：{}'.format(sub['repo'], e), 'error')
                        continue
                    report = apply_imports(self.entries, scripts, 'update')
                    for s, old_v, new_v in report['updated']:
                        self.log('更新：{}  v{} → v{}'.format(s.name, old_v, new_v), 'update')
                    for s in report['added']:
                        self.log('新增：{}  v{}'.format(s.name, s.version), 'ok')
                    for s, reason in report['skipped']:
                        self.log('跳过：{}（{}）'.format(s.name, reason), 'warn')
                    for s, err in report['errors']:
                        self.log('失败：{}：{}'.format(s.name, err), 'error')
                    sub['last_tag'] = tag
                    if sub.get('repo') == self._current_sub:
                        self._load_sub_sources(sub, silent=True)
            if has_new:
                if not self._save_entries('写入 user_api.json'):
                    return
                save_subscriptions(self.subscriptions)
                self._view_refresh_subscriptions()
                self._view_refresh_imported()
                self._view_status()
                self.log('一键订阅更新完成，重启 LX Music 后生效', 'title')
            else:
                self._view_refresh_subscriptions()

        self._run_task(work, done, '正在检查全部订阅…')

    def do_set_mirror(self, value):
        value = (value or '').strip()
        if value == '直连' or value == MIRROR_PLACEHOLDER:
            value = ''
        if value == self.settings['mirror']:
            set_mirror(value)
            return
        self.settings['mirror'] = value
        set_mirror(value)
        save_settings(self.settings)
        self.log('镜像已切换：{}'.format(value or '直连（官方 GitHub）'), 'ok')

    def do_set_downloader(self, mode):
        """切换订阅下载方式：auto（自动）/ builtin（内置）/ idm / abdm。"""
        mode = (mode or 'auto').lower()
        if mode not in self.DL_LABELS:
            mode = 'auto'
        if mode == 'idm' and not self.idm_path:
            self._info('提示', '未检测到 IDM（Internet Download Manager）')
            self._view_refresh_settings_row()
            return
        if mode == 'abdm' and not self.abdm_path:
            self._info('提示', '未检测到 AB Download Manager（ABDM）\n\n'
                               '安装后重启本工具即可自动识别，也可在设置里手动指定程序路径。')
            self._view_refresh_settings_row()
            return
        self.settings['downloader'] = mode
        self.settings['use_idm'] = mode in ('idm', 'auto')
        self.use_idm = self.settings['use_idm']
        save_settings(self.settings)
        self._view_refresh_settings_row()
        self.log('下载方式已切换为：{}'.format(self.DL_LABELS.get(mode, mode)), 'ok')

    def _on_downloader_pick(self, label):
        mode = next((k for k, v in self.DL_LABELS.items() if v == label), 'auto')
        self.do_set_downloader(mode)

    def do_pick_abdm(self):
        """手动指定 AB Download Manager 可执行文件（自动探测不到时使用）。"""
        init = os.path.dirname(self.abdm_path) if self.abdm_path else ''
        p = filedialog.askopenfilename(title='选择 AB Download Manager 的程序文件',
                                       initialdir=init or None,
                                       filetypes=[('可执行文件', '*.exe'), ('全部文件', '*.*')])
        if not p:
            return
        self.settings['abdm_path'] = p
        self.abdm_path = p
        find_abdm_path._cached = p
        save_settings(self.settings)
        self._view_refresh_settings_row()
        self.log('已指定 AB Download Manager：{}'.format(p), 'ok')

    def do_test_abdm(self):
        """测试 AB Download Manager 本地服务是否可用（端口 15151）。"""
        if not self.abdm_path:
            self._info('提示', '未检测到 AB Download Manager\n\n可在设置里手动指定其程序路径。')
            return

        def work():
            try:
                req = urllib.request.Request('http://127.0.0.1:15151/queues')
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                return ('OK', data)
            except Exception as e:
                return ('ERR', str(e))

        def done(ok, payload):
            if not ok:
                self.log('ABDM 测试失败：{}'.format(payload), 'error')
                return
            kind, data = payload
            if kind == 'OK':
                names = '、'.join(str(q.get('name')) for q in (data or [])) or '无'
                self._info('AB Download Manager 服务正常',
                           '本地服务（端口 15151）已响应。\n\n队列：{}\n\n'
                           '若下载仍无反应，请在该软件「设置 → 集成」里检查浏览器集成是否已开启。'.format(names))
                self.log('ABDM 本地服务正常，队列：{}'.format(names), 'ok')
            else:
                self._info('AB Download Manager 服务不可用',
                           '无法连接本地服务（端口 15151）：\n\n{}\n\n'
                           '请确认 AB Download Manager 正在运行；仍失败时会自动改用内置下载。'.format(data))
                self.log('ABDM 本地服务不可用：{}'.format(data), 'error')

        self._run_task(work, done, '正在测试 AB Download Manager…')

    def _downloader_status_text(self):
        """给设置页显示下载器探测结果。"""
        return 'IDM {} · ABDM {}'.format(
            '✓' if self.idm_path else '✗', '✓' if self.abdm_path else '✗')

    # ---------------- 列表行文案（名称左、次要信息右，视觉更干净、控件更少） ----------------
    def _cand_meta_text(self, s):
        parts = ['v' + (s.version or '?')]
        if s.author:
            parts.append(short(s.author, 14))
        parts.append(short(s.rel_path, 26))
        return '  ·  '.join(parts)

    def _imp_meta_text(self, e):
        parts = ['v' + str(e.get('version') or '?')]
        if e.get('author'):
            parts.append(short(e['author'], 14))
        if e.get('description'):
            parts.append(short(e['description'], 30))
        return '  ·  '.join(parts)

    def _sub_meta_text(self, sub):
        parts = []
        if (sub.get('source') or 'release') == 'repo':
            parts.append('目录' + ('/' + sub['path'] if sub.get('path') else ''))
        tag = sub.get('last_tag')
        parts.append(('当前 ' + tag) if tag else '未导入')
        return '  ·  '.join(parts)

    # ---------------- 界面共用的少量逻辑（两套 UI 完全一致，放在基类避免重复） ----------------
    def do_clear_log(self):
        self.logbox.configure(state='normal')
        self.logbox.delete('1.0', 'end')
        self.logbox.configure(state='disabled')

    def _pick_dir_to(self, entry, cb):
        d = filedialog.askdirectory(parent=self.root, title='选择文件夹',
                                    initialdir=entry.get() or self.last_folder)
        if d:
            entry.delete(0, 'end')
            entry.insert(0, d)
            cb(d)

    def _on_settings_close(self):
        try:
            self._settings_win.destroy()
        except Exception:
            pass
        self._settings_win = None

    def _cfg_selected_sub(self, what):
        sel = self.cfg_sublist.curselection()
        if not sel:
            self._info('提示', '请先选择要{}的订阅'.format(what))
            return None
        return next((s for s in self.subscriptions if s.get('repo') == self.cfg_sublist.get(sel[0])), None)

    def _open_cfg_sub_dir(self):
        sub = self._cfg_selected_sub('打开')
        if sub:
            self.do_open_download_dir(sub)

    def _delete_cfg_sub(self):
        sel = self.cfg_sublist.curselection()
        sub = self._cfg_selected_sub('删除')
        if sub:
            self.do_delete_subscription(sub)
            try:
                self.cfg_sublist.delete(sel[0])
            except Exception:
                pass

    def do_toggle_idm(self, want):
        # 兼容旧的 IDM 开关：映射为下载方式
        self.do_set_downloader('idm' if want else 'builtin')

    def _setup_placeholder(self, entry, text):
        """给输入框加灰色占位提示（例如 https://ghfast.top），兼容 tk/ttk 输入框。"""

        def set_color(color):
            try:
                entry.configure(fg=color)
            except Exception:
                try:
                    entry.configure(foreground=color)
                except Exception:
                    pass

        ph = PALETTE['faint']
        if not entry.get():
            entry.insert(0, text)
            set_color(ph)
        else:
            set_color(PALETTE['text'])

        def on_in(_e):
            if entry.get() == text:
                entry.delete(0, 'end')
                set_color(PALETTE['text'])

        def on_out(_e):
            if not entry.get():
                entry.insert(0, text)
                set_color(ph)

        entry.bind('<FocusIn>', on_in, add='+')
        entry.bind('<FocusOut>', on_out, add='+')

    def _on_mirror_preset(self, choice):
        value = '' if choice == '直连' else choice
        self.mirror_entry.delete(0, 'end')
        self.mirror_entry.insert(0, value)
        try:
            self.mirror_entry.configure(fg=PALETTE['text'])
        except Exception:
            try:
                self.mirror_entry.configure(foreground=PALETTE['text'])
            except Exception:
                pass
        self.do_set_mirror(value)

    def _sub_download_dir(self, sub):
        return os.path.join(effective_download_dir(self.settings), sub['repo'])

    def _archive_previous(self, subdir, tag, keep=True):
        """把订阅目录中的旧版本移入 history/<tag>/（keep=False 时直接清除）。
        返回处理的条目数。这样订阅根目录始终只保留最新版本，不会新旧混杂。"""
        if not os.path.isdir(subdir):
            return 0
        items = [n for n in os.listdir(subdir) if n != 'history']
        if not items:
            return 0
        name = ''.join(c for c in str(tag or 'previous') if c not in '\\/:*?"<>|').strip() or 'previous'
        moved = 0
        try:
            if keep:
                hist = os.path.join(subdir, 'history', name)
                os.makedirs(hist, exist_ok=True)
                for it in items:
                    s = os.path.join(subdir, it)
                    d = os.path.join(hist, it)
                    if os.path.isdir(s):
                        shutil.copytree(s, d, dirs_exist_ok=True)
                        shutil.rmtree(s, ignore_errors=True)
                    else:
                        shutil.move(s, d)
                    moved += 1
            else:
                for it in items:
                    s = os.path.join(subdir, it)
                    if os.path.isdir(s):
                        shutil.rmtree(s, ignore_errors=True)
                    else:
                        try:
                            os.remove(s)
                        except OSError:
                            pass
                    moved += 1
        except Exception:
            pass
        return moved

    _DL_WAIT = 180

    def _download_by_idm(self, url, target):
        """调用 IDM 下载到 target，阻塞等待文件出现（超时抛错）。"""
        folder = os.path.dirname(target) or '.'
        name = os.path.basename(target)
        os.makedirs(folder, exist_ok=True)
        subprocess.Popen([self.idm_path, '/d', mirrored_url(url), '/p', folder, '/f', name, '/n', '/s'])
        deadline = time.time() + self._DL_WAIT
        while time.time() < deadline:
            if os.path.isfile(target) and os.path.getsize(target) > 0:
                return
            time.sleep(2)
        raise ValueError('等待 IDM 下载超时（{} 秒）'.format(self._DL_WAIT))

    def _download_by_abdm(self, url, target):
        """用 AB Download Manager 下载到 target：优先本地 REST 服务，失败再退回 CLI。
        ABDM 可能按链接里的文件名保存，因此会识别目录中新出现的文件并改为目标名。"""
        folder = os.path.dirname(target) or '.'
        name = os.path.basename(target)
        os.makedirs(folder, exist_ok=True)
        try:
            before = set(os.listdir(folder))
        except OSError:
            before = set()
        m_url = mirrored_url(url)
        started = False
        try:
            body = json.dumps({'downloadSource': {'link': m_url},
                               'folder': folder.replace(chr(92), '/')}).encode('utf-8')
            req = urllib.request.Request('http://127.0.0.1:15151/start-headless-download',
                                         data=body, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
            started = True
        except Exception:
            started = False
        if not started:
            subprocess.Popen([self.abdm_path, 'download', 'add', 'http',
                              '--link=' + m_url,
                              '--folder=' + folder.replace(chr(92), '/'),
                              '--name=' + name, '--start'])
        deadline = time.time() + self._DL_WAIT
        while time.time() < deadline:
            if os.path.isfile(target) and os.path.getsize(target) > 0:
                return
            try:
                new = [f for f in os.listdir(folder)
                       if f not in before and not f.endswith(('.part', '.tmp', '.crdownload'))]
            except OSError:
                new = []
            for f in new:
                p = os.path.join(folder, f)
                try:
                    if os.path.isfile(p) and os.path.getsize(p) > 0:
                        os.replace(p, target)
                        return
                except OSError:
                    continue
            time.sleep(2)
        raise ValueError('等待 AB Download Manager 下载超时（{} 秒）'.format(self._DL_WAIT))

    def _download_url_to(self, url, target):
        """按设置的下载方式把 url 下载到 target，返回实际使用的下载器名。"""
        mode = (self.settings.get('downloader') or 'auto').lower()
        order = {'builtin': ['builtin'], 'idm': ['idm'], 'abdm': ['abdm'],
                 'auto': ['idm', 'abdm', 'builtin']}.get(mode, ['builtin'])
        for kind in order:
            if kind == 'idm' and self.idm_path:
                try:
                    self._download_by_idm(url, target)
                    return 'idm'
                except FileNotFoundError:
                    self.idm_path = None
                except Exception:
                    pass
                continue
            if kind == 'abdm' and self.abdm_path:
                try:
                    self._download_by_abdm(url, target)
                    return 'abdm'
                except FileNotFoundError:
                    self.abdm_path = None
                except Exception:
                    pass
                continue
            if kind == 'builtin':
                with open(target, 'wb') as f:
                    f.write(download_bytes(url))
                return 'builtin'
        # 外部下载器都不可用/失败时用内置兜底
        with open(target, 'wb') as f:
            f.write(download_bytes(url))
        return 'builtin'

    def _download_asset_file(self, asset, subdir):
        """把附件下载到订阅目录并返回本地路径（按设置的下载方式）。"""
        name = asset.get('name', 'asset')
        os.makedirs(subdir, exist_ok=True)
        target = os.path.join(subdir, os.path.basename(name))
        if os.path.exists(target):
            try:
                os.remove(target)
            except OSError:
                pass
        self._download_url_to(asset['browser_download_url'], target)
        return target

    def _download_repo_file(self, repo, item, subdir):
        """把仓库里的单个 .js 下载到订阅目录（复用 IDM/内置下载逻辑）。"""
        owner, name = parse_repo_ref(repo)
        path = item.get('path', '')
        fname = os.path.basename(path) or 'source.js'
        url = item.get('download_url') or 'https://raw.githubusercontent.com/{}/{}/{}/{}'.format(
            owner, name, item.get('_ref') or 'HEAD', path)
        return self._download_asset_file({'name': fname, 'browser_download_url': url}, subdir)

    def _fetch_sub_update(self, sub):
        """检查订阅是否有新版本并在后台线程完成下载。
        返回 (kind, tag, subdir, items)；kind 为 skip / noasset / new。
        支持两种来源：release（默认，读 Release 附件）与 repo（读仓库目录里的 .js）。"""
        kind = (sub.get('source') or 'release').lower()
        keep = bool(self.settings.get('keep_history', True))
        if kind == 'repo':
            files, ref = fetch_repo_files(sub['repo'], sub.get('path', ''), sub.get('branch', ''))
            rev, _date = repo_revision(sub['repo'], sub.get('path', ''), sub.get('branch', ''))
            tag = rev or ref
            if not files:
                return ('noasset', tag, None, None)
            if tag and tag == sub.get('last_tag'):
                return ('skip', tag, None, None)
            subdir = self._sub_download_dir(sub)
            self._archive_previous(subdir, sub.get('last_tag'), keep=keep)
            items = []
            for f in files:
                items.append((self._download_repo_file(sub['repo'], f, subdir), f['name']))
            return ('new', tag, subdir, items)
        rel = fetch_latest_release(*sub['repo'].split('/'))
        tag = rel.get('tag_name', '')
        if tag and tag == sub.get('last_tag'):
            return ('skip', tag, None, None)
        assets = source_assets_of(rel)
        if not assets:
            return ('noasset', tag, None, None)
        subdir = self._sub_download_dir(sub)
        self._archive_previous(subdir, sub.get('last_tag'), keep=keep)
        items = []
        for a in assets:
            items.append((self._download_asset_file(a, subdir), a.get('name', 'asset')))
        return ('new', tag, subdir, items)

    def _unzip_with_password(self, target, dest, name):
        # 解压已下载的 zip；加密时弹窗询问密码（仅主线程调用，可弹对话框）
        key = os.path.abspath(target)
        try:
            with zipfile.ZipFile(target) as zf:
                encrypted = any((info.flag_bits & 0x1) for info in zf.infolist())
        except Exception as e:
            raise ValueError('无法读取压缩包：{}'.format(e))
        if not encrypted:
            _try_zip_password(target, dest, None)
            return
        pwd = _ZIP_PASSWORDS.get(key)
        tried = 0
        while True:
            try:
                _try_zip_password(target, dest, pwd)
                if pwd:
                    _ZIP_PASSWORDS[key] = pwd
                return
            except RuntimeError:
                tried += 1
                if tried >= 5:
                    raise ValueError('多次密码错误，已放弃解压「{}」'.format(name))
                if pwd is None:
                    msg = '压缩包「{}」已加密，请输入解压密码：'.format(name)
                else:
                    msg = '解压密码不正确，请重新输入（取消则跳过）：'
                pwd = self._view_input('压缩包需要密码', msg, password=True)
                if not pwd:
                    raise ValueError('已取消解压加密压缩包「{}」'.format(name))

    def _extract_asset_main(self, target, name, src_label, subdir):
        # 主线程处理已下载附件：解压（支持加密询问）→ 删除原压缩包 → 解析脚本
        if name.lower().endswith('.zip'):
            try:
                self._unzip_with_password(target, subdir, name)
            except Exception as e:
                raise ValueError('解压失败：{}'.format(e))
            items = []
            for root2, dirs2, files2 in os.walk(subdir):
                dirs2[:] = [d for d in dirs2 if d != 'history']
                for fn in files2:
                    if fn.lower().endswith('.js'):
                        items.append(os.path.join(root2, fn))
            if not items:
                raise ValueError('压缩包内没有找到 .js 音源文件，已保留原压缩包')
            try:
                os.remove(target)
            except OSError:
                pass
        else:
            items = [target]
        scripts = []
        for p in items:
            with open(p, 'rb') as f:
                content = f.read()
            text, enc = decode_script_bytes(content)
            meta = parse_script_meta(text, fallback_name=os.path.splitext(os.path.basename(p))[0])
            scripts.append(SourceScript(p, os.path.relpath(p, subdir), text, meta, enc,
                                        _BLOCK_RE.match(text) is None))
        return scripts

    def _load_sub_sources(self, sub, silent=False):
        """把该订阅目录中「最新版本」的音源加载进待导入列表（先移除该订阅的旧条目）。
        返回 (新增数, 移除数)，目录不存在时返回 None。"""
        d = self._sub_download_dir(sub)
        if not os.path.isdir(d):
            if not silent:
                self._info('提示', '该订阅还没有本地下载\n\n请先点「一键更新」或双击该订阅下载音源。')
            return None
        base = os.path.normcase(os.path.abspath(d)) + os.sep
        keep = [s for s in self.candidates
                if not os.path.normcase(os.path.abspath(s.path)).startswith(base)]
        removed = len(self.candidates) - len(keep)
        self.candidates = keep
        self.checked_candidates = set()
        existing = {os.path.normcase(os.path.abspath(s.path)) for s in self.candidates}
        added = 0
        for s in scan_source_folder(d):
            key = os.path.normcase(os.path.abspath(s.path))
            if key in existing:
                continue
            self.candidates.append(s)
            existing.add(key)
            added += 1
        self._view_refresh_candidates()
        return (added, removed)

    def do_show_subscription_sources(self, sub):
        """单击订阅：把该订阅已下载的最新音源刷新进「待导入音源」列表。"""
        self._current_sub = sub.get('repo')
        self._view_refresh_subscriptions()
        res = self._load_sub_sources(sub)
        if res is None:
            return
        added, removed = res
        self.log('订阅「{}」：刷新本地音源（移除 {} 个旧条目，加载 {} 个）'.format(sub['repo'], removed, added),
                 'ok' if added else 'warn')

    def _download_root(self):
        return os.path.normcase(os.path.abspath(effective_download_dir(self.settings))) + os.sep

    def sub_of_path(self, path):
        # 根据文件路径反查它属于哪个订阅（订阅名是 owner/repo，需按完整下载目录匹配）
        p = os.path.normcase(os.path.abspath(path))
        best, best_len = None, -1
        for s in self.subscriptions:
            d = os.path.normcase(os.path.abspath(self._sub_download_dir(s))) + os.sep
            if p.startswith(d) and len(d) > best_len:
                best, best_len = s, len(d)
        return best

    def history_versions_of_file(self, path):
        # 列出与给定文件同名的历史版本 [(tag, 路径)]（新 → 旧）
        sub = self.sub_of_path(path)
        if not sub:
            return []
        d = self._sub_download_dir(sub)
        hist_root = os.path.join(d, 'history')
        if not os.path.isdir(hist_root):
            return []
        try:
            rel = os.path.relpath(path, d)
        except ValueError:
            return []
        parts = rel.split(os.sep)
        if parts and parts[0] == 'history':
            rel = os.path.join(*parts[2:]) if len(parts) > 2 else os.path.basename(path)
        out = []
        for tag in sorted(os.listdir(hist_root), reverse=True):
            vdir = os.path.join(hist_root, tag)
            if not os.path.isdir(vdir):
                continue
            cand = os.path.join(vdir, rel)
            if os.path.isfile(cand):
                out.append((tag, cand))
        return out

    def load_file_as_candidate(self, path, label=''):
        # 把磁盘上的某个 .js 读进待导入列表（供历史版本切换使用）
        if not os.path.isfile(path):
            self._info('提示', '文件不存在：{}'.format(path))
            return False
        key = os.path.normcase(os.path.abspath(path))
        if any(os.path.normcase(os.path.abspath(s.path)) == key for s in self.candidates):
            self.log('「{}」已在待导入列表中'.format(os.path.basename(path)), 'warn')
            return False
        text, enc = read_text_auto(path)
        meta = parse_script_meta(text, fallback_name=os.path.splitext(os.path.basename(path))[0])
        sub = self.sub_of_path(path)
        base = self._sub_download_dir(sub) if sub else os.path.dirname(path)
        try:
            rel = os.path.relpath(path, base)
        except ValueError:
            rel = os.path.basename(path)
        self.candidates.append(SourceScript(path, rel, text, meta, enc, _BLOCK_RE.match(text) is None))
        self._view_refresh_candidates()
        self.log('已载入历史版本{}：{}  v{}'.format(label, meta.get('name'), meta.get('version')), 'ok')
        return True

    def versions_for_entry(self, entry):
        # 在全部订阅的最新版本与历史版本中，查找与已导入音源同名的可切换版本
        target = normalize_name(entry.get('name', ''))
        out = []
        for sub in self.subscriptions:
            d = self._sub_download_dir(sub)
            if not os.path.isdir(d):
                continue
            found = []
            for s in scan_source_folder(d):
                if normalize_name(s.name) == target:
                    found.append((sub.get('last_tag') or '最新', s.path))
            hist_root = os.path.join(d, 'history')
            if os.path.isdir(hist_root):
                for tag in sorted(os.listdir(hist_root), reverse=True):
                    vdir = os.path.join(hist_root, tag)
                    if not os.path.isdir(vdir):
                        continue
                    for s in scan_source_folder(vdir):
                        if normalize_name(s.name) == target:
                            found.append((tag, s.path))
            for tag, p in found:
                out.append(('{} · {}'.format(sub['repo'], tag), p))
        return out

    def switch_entry_script(self, entry, path):
        # 把已导入音源切换为指定文件（历史版本回退 / 前移）
        if not os.path.isfile(path):
            self._info('提示', '文件不存在：{}'.format(path))
            return
        text, _enc = read_text_auto(path)
        meta = parse_script_meta(text, fallback_name=os.path.splitext(os.path.basename(path))[0])
        comp = compress_script(text)
        if (entry.get('script') or '') == comp:
            self._info('提示', '当前已经是这个版本，无需切换')
            return
        if not self._auto_backup():
            return
        old_v = entry.get('version', '?')
        entry['name'] = meta.get('name') or entry.get('name')
        entry['description'] = meta.get('description', entry.get('description', ''))
        entry['version'] = meta.get('version', entry.get('version', ''))
        entry['author'] = meta.get('author', entry.get('author', ''))
        entry['homepage'] = meta.get('homepage', entry.get('homepage', ''))
        entry['script'] = comp
        if not self._save_entries('切换音源版本'):
            return
        self._view_refresh_imported()
        self._view_status()
        self.log('已切换「{}」：v{} → v{}'.format(entry.get('name'), old_v, entry.get('version')), 'update')

    def _popup_menu(self, event, items):
        # 通用右键菜单：None=分隔线；(label, 回调)=命令；(label, None)=禁用；
        # (label, [子项…])=级联子菜单
        C = self.C
        font = getattr(self, 'f_small', None)

        def build(parent, rows):
            for row in rows:
                if row is None:
                    parent.add_separator()
                    continue
                label, action = row[0], row[1]
                if isinstance(action, (list, tuple)):
                    sub = tk.Menu(parent, tearoff=0, bg=C['card'], fg=C['text'],
                                  activebackground=C['card2'], activeforeground=C['text'],
                                  bd=0, relief='flat', font=font)
                    build(sub, action)
                    parent.add_cascade(label=label, menu=sub)
                elif action is None:
                    parent.add_command(label=label, state='disabled')
                else:
                    parent.add_command(label=label, command=action)

        menu = tk.Menu(self.root, tearoff=0, bg=C['card'], fg=C['text'],
                       activebackground=C['card2'], activeforeground=C['text'],
                       bd=0, relief='flat', font=font)
        build(menu, items)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def show_candidate_menu(self, event, i):
        # 待导入音源右键：历史版本切换 / 查看详情
        if not (0 <= i < len(self.candidates)):
            return
        s = self.candidates[i]
        vers = self.history_versions_of_file(s.path)
        rows = []
        if vers:
            rows.append(('历史版本（{} 个）'.format(len(vers)),
                         [('v{}'.format(t), (lambda p=p: self.load_file_as_candidate(p, ''))) for t, p in vers]))
        else:
            rows.append(('无历史版本', None))
        rows.append(None)
        rows.append(('查看详情', lambda: self._cand_detail(i)))
        self._popup_menu(event, rows)

    def show_imported_menu(self, event, i):
        # 已导入音源右键：在订阅的历史版本之间切换
        if not (0 <= i < len(self.entries)):
            return
        e = self.entries[i]
        vers = self.versions_for_entry(e)
        rows = []
        if vers:
            rows.append(('切换版本（{} 个）'.format(len(vers)),
                         [(lbl, (lambda p=p: self.switch_entry_script(e, p))) for lbl, p in vers]))
        else:
            rows.append(('无可切换版本', None))
        rows.append(None)
        rows.append(('查看详情', lambda: self._imported_detail(i)))
        self._popup_menu(event, rows)

    def show_sub_menu(self, event, i):
        # 订阅右键：载入最新音源 / 更新 / 打开目录 / 删除
        if not (0 <= i < len(self.subscriptions)):
            return
        sub = self.subscriptions[i]
        self._popup_menu(event, [
            ('载入最新音源', lambda: self.do_show_subscription_sources(sub)),
            ('立即检查更新', lambda: self.do_update_subscription(sub)),
            None,
            ('打开下载目录', lambda: self.do_open_download_dir(sub)),
            ('删除订阅', lambda: self.do_delete_subscription(sub)),
        ])

    def do_open_download_dir(self, sub=None):
        d = self._sub_download_dir(sub) if sub else effective_download_dir(self.settings)
        self._open_dir(d)

    def do_delete_subscription(self, sub):
        if not self._confirm('确认删除订阅？', '将删除订阅「{}」。\n\n已下载的音源文件不会被删除。'.format(sub.get('repo'))):
            return
        self.subscriptions = [s for s in self.subscriptions if s.get('repo') != sub.get('repo')]
        if self._current_sub == sub.get('repo'):
            self._current_sub = None
        save_subscriptions(self.subscriptions)
        self._view_refresh_subscriptions()
        self.log('已删除订阅「{}」'.format(sub.get('repo')), 'ok')

    # ---------------- 配置 ----------------
    def apply_settings(self):
        """配置变更后刷新主界面（备份卡片/日志窗口显隐等）。"""
        try:
            self.backup_dir = effective_backup_dir(self.settings)
            self.backups = BackupManager(self.backup_dir)
            self._view_apply_backup_visible()
            self._view_apply_log_visible()
            self._view_rebalance_bottom()
            self._view_refresh_settings_row()
            self._view_status()
        except Exception as e:
            self.log('应用配置失败：{}'.format(e), 'error')

    def do_set_backup_enabled(self, enable):
        self.settings['backup_enabled'] = bool(enable)
        save_settings(self.settings)
        self.log('自动备份已{}'.format('开启' if enable else '关闭'), 'ok')
        self.apply_settings()

    def do_set_backup_dir(self, path):
        path = (path or '').strip()
        default_dir = os.path.join(config_dir(), 'backups')
        if not path:
            path = default_dir
            try:
                os.makedirs(path, exist_ok=True)
            except Exception:
                pass
        if not os.path.isdir(path):
            self._info('提示', '目录不存在，请重新选择')
            return
        old = effective_backup_dir(self.settings)
        if path == old:
            return
        if old and os.path.isdir(old) and os.path.normcase(os.path.abspath(old)) != os.path.normcase(os.path.abspath(path)):
            files = [f for f in os.listdir(old) if f.lower().endswith('.json')]
            if files:
                if not self._confirm('迁移旧备份？', '检测到旧备份目录中还有 {} 个备份文件。\n\n是否将旧备份迁移到新目录？'.format(len(files))):
                    return
                try:
                    os.makedirs(path, exist_ok=True)
                    moved = 0
                    for fn in files:
                        s = os.path.join(old, fn)
                        if os.path.isfile(s):
                            shutil.copy2(s, os.path.join(path, fn))
                            moved += 1
                    self.log('已迁移 {} 个备份文件到：{}'.format(moved, path), 'ok')
                except Exception as e:
                    self.log('迁移失败：{}'.format(e), 'error')
                    return
        # 等于默认目录时归一化为空串（表示“使用默认”）
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(default_dir)):
            self.settings['backup_dir'] = ''
            self.log('备份文件夹已恢复为默认（config/backups）', 'ok')
        else:
            self.settings['backup_dir'] = path
            self.log('备份文件夹已改为：{}'.format(path), 'ok')
        save_settings(self.settings)
        self.apply_settings()

    def do_set_download_dir(self, path):
        path = (path or '').strip()
        if path and not os.path.isdir(path):
            self._info('提示', '目录不存在，请重新选择')
            return
        self.settings['download_dir'] = path
        save_settings(self.settings)
        self.log('订阅下载目录已改为：{}'.format(path or '（默认下载目录/lxsubscribe）'), 'ok')

    def do_set_keep_history(self, enable):
        self.settings['keep_history'] = bool(enable)
        save_settings(self.settings)
        self.log('历史订阅保存已{}'.format('开启（更新前归档旧版本到 history 子目录）' if enable else '关闭'), 'ok')

    def do_set_log_enabled(self, enable):
        self.settings['log_enabled'] = bool(enable)
        if not enable:
            self.settings['log_window'] = False
        save_settings(self.settings)
        self.log('日志记录已{}'.format('开启' if enable else '关闭'), 'ok')
        self.apply_settings()
        self._view_refresh_cfg_logwin()

    def do_set_log_window(self, enable):
        if enable and not self.settings.get('log_enabled', True):
            self._info('提示', '请先开启「记录日志」才能显示日志窗口')
            return
        self.settings['log_window'] = bool(enable)
        save_settings(self.settings)
        self.apply_settings()

    def do_open_settings(self):
        raise NotImplementedError

    # ---------------- 其他 ----------------
    def do_relocate(self):
        p = self._view_ask_file()
        if not p:
            return
        self.user_api_path = p
        self._load_data()

    def do_open_data_dir(self):
        self._open_dir(os.path.dirname(self.user_api_path) if self.user_api_path else '')

    def do_open_backup_dir(self):
        self._open_dir(self.backup_dir)

    def _open_dir(self, d):
        try:
            if d and os.path.isdir(d):
                os.startfile(d)
            else:
                self.log('目录不存在，无法打开', 'warn')
        except Exception as e:
            self.log('打开目录失败：{}'.format(e), 'error')

    def _cand_detail(self, i):
        if not (0 <= i < len(self.candidates)):
            return
        s = self.candidates[i]
        body = ('名称：{}\n版本：{}\n作者：{}\n描述：{}\n主页：{}\n\n文件：{}\n编码：{}\n脚本大小：{} 字符\n\n'
                '———————— 脚本内容预览 ————————\n\n{}'.format(
                    s.name, s.version, s.author or '（无）', s.description or '（无）', s.homepage or '（无）',
                    s.path, s.encoding, len(s.raw), s.raw[:3000]))
        self._view_show_detail('音源详情 - {}'.format(s.name), body)

    def _imported_detail(self, i):
        if not (0 <= i < len(self.entries)):
            return
        e = self.entries[i]
        try:
            raw = decompress_script(e.get('script') or '')
        except Exception as ex:
            raw = '(脚本解压失败：{})'.format(ex)
        body = ('ID：{}\n名称：{}\n版本：{}\n作者：{}\n主页：{}\n描述：{}\n更新提示：{}\n'
                '脚本大小：{} 字符（压缩存储 {} 字符）\n\n———————— 脚本内容预览 ————————\n\n{}'.format(
                    e.get('id', '（无）'), e.get('name', ''), e.get('version', ''),
                    e.get('author') or '（无）', e.get('homepage') or '（无）', e.get('description') or '（无）',
                    '开启' if e.get('allowShowUpdateAlert') else '关闭',
                    len(raw), len(e.get('script') or ''), raw[:3000]))
        self._view_show_detail('音源详情 - {}'.format(e.get('name', '')), body)

    def on_close(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()

    # ---------------- UI 需实现的方法 ----------------
    def _view_log(self, text, level='info'):
        raise NotImplementedError

    def _view_set_status(self, text):
        raise NotImplementedError

    def _view_refresh_candidates(self):
        raise NotImplementedError

    def _view_refresh_imported(self):
        raise NotImplementedError

    def _view_refresh_backups(self):
        raise NotImplementedError

    def _view_refresh_subscriptions(self):
        raise NotImplementedError

    def _view_apply_backup_visible(self):
        raise NotImplementedError

    def _view_apply_log_visible(self):
        raise NotImplementedError

    def _view_refresh_settings_row(self):
        pass

    def _view_rebalance_bottom(self):
        pass

    def _view_refresh_cfg_logwin(self):
        pass

    def _view_input(self, title, prompt, password=False):
        raise NotImplementedError

    def _view_confirm(self, title, message, danger=False):
        raise NotImplementedError

    def _view_info(self, title, message):
        raise NotImplementedError

    def _view_show_detail(self, title, text):
        raise NotImplementedError

    def _view_ask_folder(self):
        raise NotImplementedError

    def _view_ask_file(self):
        raise NotImplementedError


# ---------------------------------------------------------------- customtkinter 界面
_SMOOTH_FRAME_CLASS = None


def smooth_scrollable_class():
    """返回带惯性平滑滚动的 CTkScrollableFrame 子类（覆盖官方逐格滚动）。"""
    global _SMOOTH_FRAME_CLASS
    if _SMOOTH_FRAME_CLASS is not None:
        return _SMOOTH_FRAME_CLASS
    import customtkinter as ctk

    class SmoothScrollableFrame(ctk.CTkScrollableFrame):
        FRAME_MS = 33  # 30fps：每帧完整重绘，避免拖尾

        def __init__(self, *args, **kwargs):
            self._smooth_vel = 0.0
            self._smooth_after = None
            super().__init__(*args, **kwargs)

        def _mouse_wheel_all(self, event):
            if not self._check_if_valid_scroll(event.widget):
                return
            if getattr(self, '_shift_pressed', False):
                return
            y0, y1 = self._parent_canvas.yview()
            at_top = y0 <= 0.0 and event.delta > 0
            at_bottom = y1 >= 1.0 and event.delta < 0
            if at_top or at_bottom:
                return
            self._smooth_vel += -event.delta / 120.0 * 9.0
            self._smooth_start()

        def _smooth_start(self):
            if self._smooth_after is None:
                self._smooth_after = self.after(self.FRAME_MS, self._smooth_step)

        def _smooth_step(self):
            self._smooth_after = None
            self._smooth_vel *= 0.8
            if abs(self._smooth_vel) < 0.4:
                self._smooth_vel = 0.0
                return
            step = self._smooth_vel
            if abs(step) < 3:
                step = 3 if step > 0 else -3  # 步长量化：避免 1px 高频滚动残影
            try:
                self._parent_canvas.yview('scroll', int(round(step)), 'units')
                y0, y1 = self._parent_canvas.yview()
                if (y0 <= 0.0 and self._smooth_vel < 0) or (y1 >= 1.0 and self._smooth_vel > 0):
                    self._smooth_vel = 0.0
                    return
            except Exception:
                return
            self._smooth_after = self.after(self.FRAME_MS, self._smooth_step)

        def destroy(self):
            if self._smooth_after is not None:
                try:
                    self.after_cancel(self._smooth_after)
                except Exception:
                    pass
            super().destroy()

    _SMOOTH_FRAME_CLASS = SmoothScrollableFrame
    return _SMOOTH_FRAME_CLASS


def ensure_customtkinter():
    try:
        import customtkinter  # noqa: F401
        return True
    except Exception:
        pass
    print('首次运行：正在自动安装界面组件 customtkinter，请稍候…')
    try:
        import subprocess
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                        '--quiet', 'customtkinter'], capture_output=True, text=True, check=True)
        import customtkinter  # noqa: F401
        print('安装完成。')
        return True
    except Exception:
        print('customtkinter 安装失败，将使用内置 ttk 界面。')
        return False


class CtkApp(BaseApp):
    def __init__(self, user_api_path=None, backup_dir=None, auto_confirm=False, hidden=False):
        import customtkinter as ctk
        self.ctk = ctk
        self.C = PALETTE
        # 禁用 CTk 自动 DPI 缩放：固定 1:1 渲染，避免高 DPI 屏上窗口超出屏幕、布局被撑破
        try:
            ctk.deactivate_automatic_dpi_awareness()
        except Exception:
            pass
        try:
            ctk.set_widget_scaling(1.0)
            ctk.set_window_scaling(1.0)
        except Exception:
            pass
        self.animations = not hidden
        self.SmoothFrame = smooth_scrollable_class()
        self.settings = load_settings()
        set_mirror(self.settings['mirror'])
        self.use_idm = self.settings['use_idm']
        self.idm_path = find_idm_path()
        self.abdm_path = self.settings.get('abdm_path') or find_abdm_path()
        ctk.set_appearance_mode('light')
        ctk.set_default_color_theme('blue')
        self.root = ctk.CTk(fg_color=self.C['bg'])
        if hidden:
            self.root.withdraw()
        self.root.title(APP_TITLE)
        self.root.geometry('1220x800')
        self.root.minsize(1100, 720)
        self.icon = _make_icon()
        self._icon_small = _make_icon(zoom=1)
        try:
            self.root.iconphoto(True, self.icon)
        except Exception:
            pass
        self.path_label = None
        self.folder_label = None
        self._build()
        super().__init__(user_api_path=user_api_path, backup_dir=backup_dir, auto_confirm=auto_confirm)
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

    # ---------------- 构建 ----------------
    def _btn(self, master, text, command, kind='ghost', width=None):
        cfg = dict(width=width or 92, height=30, corner_radius=6, font=self.f_btn, command=command, text=text)
        if kind == 'primary':
            cfg.update(fg_color=self.C['accent'], hover_color=self.C['accent_hover'], text_color='#fffaf5')
        elif kind == 'danger':
            cfg.update(fg_color=self.C['danger'], hover_color='#cf7278', text_color='#fffaf5')
        else:
            cfg.update(fg_color='transparent', hover_color=self.C['hover'], text_color=self.C['text'],
                       border_width=1, border_color=self.C['border'])
        return self.ctk.CTkButton(master, **cfg)

    def _build(self):
        ctk, C = self.ctk, self.C
        self.f_title = ctk.CTkFont(family=FONT_FAMILY, size=17, weight='bold')
        self.f_card = ctk.CTkFont(family=FONT_FAMILY, size=14, weight='bold')
        self.f_base = ctk.CTkFont(family=FONT_FAMILY, size=13)
        self.f_bold = ctk.CTkFont(family=FONT_FAMILY, size=13, weight='bold')
        self.f_small = ctk.CTkFont(family=FONT_FAMILY, size=12)
        self.f_tiny = ctk.CTkFont(family=FONT_FAMILY, size=11)
        self.f_btn = ctk.CTkFont(family=FONT_FAMILY, size=13)
        self.f_log = ctk.CTkFont(family=FONT_FAMILY, size=12)

        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # ---------- 顶栏 ----------
        header = ctk.CTkFrame(self.root, fg_color=C['card'], corner_radius=8)
        header.grid(row=0, column=0, sticky='ew', padx=14, pady=(12, 6))
        header.grid_columnconfigure(2, weight=1)
        tk.Label(header, image=self._icon_small, bg=C['card'], borderwidth=0).grid(row=0, column=0, rowspan=2, padx=(16, 10), pady=(10, 10))
        ctk.CTkLabel(header, text='LX Music 音源一键导入 / 更新工具', font=self.f_title, text_color=C['text']).grid(
            row=0, column=1, sticky='w', pady=(12, 2))
        ctk.CTkLabel(header, text='洛雪音乐桌面版 · 自定义音源批量导入、更新、备份与清除',
                     font=self.f_tiny, text_color=C['muted']).grid(row=1, column=1, sticky='w', pady=(0, 12))
        self.path_label = ctk.CTkLabel(header, text='', font=self.f_tiny, text_color=C['faint'], anchor='e')
        self.path_label.grid(row=0, column=2, rowspan=2, sticky='e', padx=(8, 12))
        btns = ctk.CTkFrame(header, fg_color='transparent')
        btns.grid(row=0, column=3, rowspan=2, sticky='e', padx=(0, 14), pady=10)
        self._btn(btns, '⚙', self.do_open_settings, width=36).pack(side='left', padx=(0, 8))
        self._btn(btns, '重新定位', self.do_relocate, width=84).pack(side='left', padx=(0, 8))
        self._btn(btns, '打开数据目录', self.do_open_data_dir, width=100).pack(side='left')

        # ---------- 主区 ----------
        main = ctk.CTkFrame(self.root, fg_color='transparent')
        main.grid(row=1, column=0, sticky='nsew', padx=14, pady=6)
        main.grid_columnconfigure((0, 1), weight=1, uniform='col')
        main.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(main, fg_color=C['card'], corner_radius=8)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 7))
        right = ctk.CTkFrame(main, fg_color=C['card'], corner_radius=8)
        right.grid(row=0, column=1, sticky='nsew', padx=(7, 0))
        self._build_left_card(left)
        self._build_right_card(right)

        # ---------- 底部（备份 + 日志） ----------
        bottom = ctk.CTkFrame(self.root, fg_color='transparent')
        bottom.grid(row=2, column=0, sticky='ew', padx=14, pady=(6, 4))
        bottom.grid_columnconfigure(0, weight=2, uniform='bot')
        bottom.grid_columnconfigure(1, weight=3, uniform='bot')
        bottom.grid_columnconfigure(2, weight=3, uniform='bot')
        self._bottom = bottom
        self._build_bottom(bottom)

        # ---------- 状态栏 ----------
        status = ctk.CTkFrame(self.root, fg_color='transparent')
        status.grid(row=3, column=0, sticky='ew', padx=14, pady=(0, 10))
        status.grid_columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value='')
        ctk.CTkLabel(status, textvariable=self.status_var, font=self.f_tiny, text_color=C['faint'],
                     anchor='w').grid(row=0, column=0, sticky='w')
        ctk.CTkLabel(status, text='所有写操作前自动备份；修改后需重启 LX Music 生效',
                     font=self.f_tiny, text_color=C['faint']).grid(row=0, column=1, sticky='e')

    def _build_left_card(self, card):
        ctk, C = self.ctk, self.C
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)

        head = ctk.CTkFrame(card, fg_color='transparent')
        head.grid(row=0, column=0, sticky='ew', padx=14, pady=(12, 4))
        head.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(head, text='待导入音源', font=self.f_card, text_color=C['text']).grid(row=0, column=0, sticky='w')
        self.folder_label = ctk.CTkLabel(head, text='尚未选择文件夹', font=self.f_tiny, text_color=C['faint'], anchor='e')
        self.folder_label.grid(row=0, column=1, sticky='e')

        bar = ctk.CTkFrame(card, fg_color='transparent')
        bar.grid(row=1, column=0, sticky='ew', padx=14, pady=(4, 2))
        self._btn(bar, '选择音源文件夹', self.do_scan_folder, kind='primary', width=122).pack(side='left', padx=(0, 6))
        self._btn(bar, '全选', lambda: self.do_select_all_candidates(True), width=56).pack(side='left', padx=4)
        self._btn(bar, '全不选', lambda: self.do_select_all_candidates(False), width=62).pack(side='left', padx=4)
        self._btn(bar, '移除所选', self.do_remove_candidates, width=78).pack(side='left', padx=4)
        self._btn(bar, '清空列表', self.do_clear_candidates, width=78).pack(side='left', padx=4)

        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', lambda *a: self._on_search())
        ctk.CTkEntry(card, textvariable=self.search_var,
                     placeholder_text='搜索音源名称 / 作者 / 路径…',
                     placeholder_text_color=C['muted'],
                     height=30, corner_radius=6, fg_color=C['field'], border_color=C['border'], border_width=1,
                     text_color=C['text'], font=self.f_small).grid(
            row=2, column=0, sticky='ew', padx=14, pady=(2, 4))

        # 隔离容器：CTk 滚动条默认请求高度 200px，会撑破布局，用固定容器隔绝其影响
        _cand_holder = tk.Frame(card, bg=C['card'])
        _cand_holder.grid_propagate(False)
        _cand_holder.grid(row=3, column=0, sticky='nsew', padx=10, pady=2)
        self.cand_list = self.SmoothFrame(_cand_holder, fg_color=C['card'], corner_radius=0,
                                          scrollbar_button_color=C['border'], scrollbar_button_hover_color=C['faint'])
        self.cand_list.pack(fill='both', expand=True)
        self.cand_rows = {}

        seg_row = ctk.CTkFrame(card, fg_color='transparent')
        seg_row.grid(row=4, column=0, sticky='ew', padx=14, pady=(8, 0))
        ctk.CTkLabel(seg_row, text='导入模式', font=self.f_small, text_color=C['muted']).pack(side='left', padx=(0, 8))
        self.mode_var = tk.StringVar(value=MODE_ADD_LABEL)
        self.mode_seg = ctk.CTkSegmentedButton(
            seg_row, values=[MODE_ADD_LABEL, MODE_UPDATE_LABEL], variable=self.mode_var,
            command=lambda v: self._set_mode(v), height=30, corner_radius=6,
            selected_color=C['accent'], selected_hover_color=C['accent_hover'],
            unselected_color=C['card'], unselected_hover_color=C['hover'],
            fg_color=C['card'], text_color=C['text'], font=self.f_small)
        self.mode_seg.pack(side='left')

        act = ctk.CTkFrame(card, fg_color='transparent')
        act.grid(row=5, column=0, sticky='ew', padx=14, pady=(10, 2))
        self.btn_import_sel = self._btn(act, '导入所选', self.do_import, kind='primary', width=116)
        self.btn_import_sel.pack(side='left', padx=(0, 8))
        self.btn_import_all = self._btn(act, '一键全部导入', lambda: self.do_import(all_selected=True), width=132)
        self.btn_import_all.pack(side='left')
        self.cand_count = ctk.CTkLabel(act, text='', font=self.f_tiny, text_color=C['muted'])
        self.cand_count.pack(side='right')

        ctk.CTkLabel(card, text='提示：全选作用于当前显示的音源（受搜索过滤）；「一键全部」作用于全部待导入音源；双击音源查看详情',
                     font=self.f_tiny, text_color=C['faint'], anchor='w').grid(
            row=6, column=0, sticky='w', padx=14, pady=(4, 10))

    def _build_right_card(self, card):
        ctk, C = self.ctk, self.C
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(card, fg_color='transparent')
        head.grid(row=0, column=0, sticky='ew', padx=14, pady=(12, 4))
        head.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(head, text='已导入音源', font=self.f_card, text_color=C['text']).grid(row=0, column=0, sticky='w')
        self.imp_count = ctk.CTkLabel(head, text='', font=self.f_small, text_color=C['muted'])
        self.imp_count.grid(row=0, column=1, sticky='e', padx=(0, 8))
        self._btn(head, '刷新', self._view_refresh_imported, width=62).grid(row=0, column=2, sticky='e')

        _imp_holder = tk.Frame(card, bg=C['card'])
        _imp_holder.grid_propagate(False)
        _imp_holder.grid(row=2, column=0, sticky='nsew', padx=10, pady=2)
        self.imp_list = self.SmoothFrame(_imp_holder, fg_color=C['card'], corner_radius=0,
                                         scrollbar_button_color=C['border'], scrollbar_button_hover_color=C['faint'])
        self.imp_list.pack(fill='both', expand=True)
        self.imp_rows = {}

        act = ctk.CTkFrame(card, fg_color='transparent')
        act.grid(row=3, column=0, sticky='ew', padx=14, pady=(8, 2))
        self._btn(act, '删除所选', self.do_delete_imported, width=96).pack(side='left', padx=(0, 8))
        self._btn(act, '一键清除全部', self.do_clear_imported, kind='danger', width=120).pack(side='left')
        ctk.CTkLabel(act, text='勾选后点击删除；双击查看详情', font=self.f_tiny, text_color=C['faint']).pack(side='right')

        ctk.CTkLabel(card, text='提示：修改 user_api.json 后需重启 LX Music 桌面版才会生效',
                     font=self.f_tiny, text_color=C['faint'], anchor='w').grid(
            row=4, column=0, sticky='w', padx=14, pady=(4, 10))

    def _build_bottom(self, bottom):
        ctk, C = self.ctk, self.C

        bk = ctk.CTkFrame(bottom, fg_color=C['card'], corner_radius=8)
        bk.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        self._bk_card = bk
        bk.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(bk, fg_color='transparent')
        head.grid(row=0, column=0, sticky='ew', padx=14, pady=(12, 2))
        head.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(head, text='备份文件', font=self.f_card, text_color=C['text']).grid(row=0, column=0, sticky='w')
        btns = ctk.CTkFrame(head, fg_color='transparent')
        btns.grid(row=0, column=1, sticky='e')
        self._btn(btns, '生成备份', self.do_backup, width=68).pack(side='left', padx=2)
        self._btn(btns, '还原所选', self.do_restore_backup, kind='primary', width=68).pack(side='left', padx=2)
        self._btn(btns, '打开文件夹', self.do_open_backup_dir, width=78).pack(side='left', padx=2)
        self._btn(btns, '删除所选', self.do_delete_backups, width=68).pack(side='left', padx=2)
        self._btn(btns, '清空备份', self.do_clear_backups, width=68).pack(side='left', padx=2)
        _bk_holder = tk.Frame(bk, bg=C['card'], height=112)
        _bk_holder.pack_propagate(False)
        _bk_holder.grid(row=1, column=0, sticky='ew', padx=10, pady=(2, 10))
        self.bk_list = self.SmoothFrame(_bk_holder, fg_color=C['card'], corner_radius=0,
                                        scrollbar_button_color=C['border'], scrollbar_button_hover_color=C['faint'])
        self.bk_list.pack(fill='both', expand=True)
        self.bk_rows = {}

        sub = ctk.CTkFrame(bottom, fg_color=C['card'], corner_radius=8)
        sub.grid(row=0, column=1, sticky='nsew', padx=(6, 6))
        self._sub_card = sub
        sub.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(sub, fg_color='transparent')
        head.grid(row=0, column=0, sticky='ew', padx=14, pady=(12, 2))
        head.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(head, text='订阅更新', font=self.f_card, text_color=C['text']).grid(row=0, column=0, sticky='w')
        btns = ctk.CTkFrame(head, fg_color='transparent')
        btns.grid(row=0, column=1, sticky='e')
        self._btn(btns, '添加订阅', self.do_add_subscription, kind='primary', width=66).pack(side='left', padx=2)
        self._btn(btns, '检查更新', self.do_check_subscriptions, width=66).pack(side='left', padx=2)
        self._btn(btns, '一键更新', self.do_update_all_subscriptions, width=66).pack(side='left', padx=2)
        self._btn(btns, '打开目录', self.do_open_download_dir, width=66).pack(side='left', padx=2)
        _sub_holder = tk.Frame(sub, bg=C['card'], height=112)
        _sub_holder.pack_propagate(False)
        _sub_holder.grid(row=1, column=0, sticky='ew', padx=10, pady=(2, 10))
        self.sub_list = self.SmoothFrame(_sub_holder, fg_color=C['card'], corner_radius=0,
                                         scrollbar_button_color=C['border'], scrollbar_button_hover_color=C['faint'])
        self.sub_list.pack(fill='both', expand=True)
        self.sub_rows = {}

        setrow = tk.Frame(sub, bg=C['card'])
        setrow.grid(row=2, column=0, sticky='ew', padx=14, pady=(0, 8))
        tk.Label(setrow, text='镜像', bg=C['card'], fg=C['muted'], font=self.f_tiny).pack(side='left')
        self.mirror_entry = tk.Entry(setrow, bg=C['field'], fg=C['text'],
                                     insertbackground=C['text'], relief='flat', highlightthickness=1,
                                     highlightbackground=C['border'], highlightcolor=C['accent'],
                                     font=self.f_tiny, width=17)
        self.mirror_entry.pack(side='left', padx=6)
        self.mirror_entry.insert(0, self.settings['mirror'])
        self._setup_placeholder(self.mirror_entry, MIRROR_PLACEHOLDER)
        self.mirror_entry.bind('<Return>', lambda e: self.do_set_mirror(self.mirror_entry.get()))
        self.mirror_entry.bind('<FocusOut>', lambda e: self.do_set_mirror(self.mirror_entry.get()))
        self.mirror_combo = ctk.CTkOptionMenu(
            setrow, values=['直连', 'gh-proxy.com', 'ghfast.top', 'ghproxy.net', 'gh.api.99988866.xyz'],
            command=self._on_mirror_preset, height=28, corner_radius=6,
            fg_color=C['field'], button_color=C['accent'], button_hover_color=C['accent_hover'],
            text_color=C['text'], dropdown_fg_color=C['card'], dropdown_hover_color=C['hover'],
            dropdown_text_color=C['text'], font=self.f_tiny)
        self.mirror_combo.pack(side='left', padx=6)
        tk.Label(setrow, text='下载', bg=C['card'], fg=C['faint'], font=self.f_tiny).pack(side='left', padx=(10, 4))
        self.dl_var = tk.StringVar(value=self.DL_LABELS.get(self.settings.get('downloader', 'auto'), '自动'))
        self.dl_menu = ctk.CTkOptionMenu(setrow, values=list(self.DL_LABELS.values()),
                                         variable=self.dl_var, width=104, height=26,
                                         font=self.f_tiny, dropdown_font=self.f_tiny,
                                         fg_color=C['field'], button_color=C['border'],
                                         button_hover_color=C['hover'], text_color=C['text'],
                                         dropdown_fg_color=C['card'], dropdown_hover_color=C['card2'],
                                         dropdown_text_color=C['text'],
                                         command=self._on_downloader_pick)
        self.dl_menu.pack(side='left', padx=(0, 6), pady=5)

        lg = ctk.CTkFrame(bottom, fg_color=C['card'], corner_radius=8)
        lg.grid(row=0, column=2, sticky='nsew', padx=(6, 0))
        self._lg_card = lg
        lg.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(lg, fg_color='transparent')
        head.grid(row=0, column=0, sticky='ew', padx=14, pady=(12, 2))
        head.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(head, text='运行日志', font=self.f_card, text_color=C['text']).grid(row=0, column=0, sticky='w')
        self._btn(head, '清空日志', self.do_clear_log, width=80).grid(row=0, column=1, sticky='e')
        _lg_holder = tk.Frame(lg, bg=C['field'], height=112)
        _lg_holder.pack_propagate(False)
        _lg_holder.grid(row=1, column=0, sticky='ew', padx=10, pady=(2, 10))
        self.logbox = ctk.CTkTextbox(_lg_holder, fg_color=C['field'], corner_radius=6, font=self.f_log,
                                     wrap='word', state='disabled')
        self.logbox.pack(fill='both', expand=True)
        for tag, color in LOG_COLORS.items():
            self.logbox.tag_config(tag, foreground=color)

    # ---------------- 动画 ----------------
    def _set_row_color(self, widget, color):
        """立即设置行背景并同步子组件（悬停反馈无动画，进出必然复位，不残留）。"""
        try:
            attr = 'fg_color' if 'fg_color' in widget.keys() else 'bg'
            widget.configure(**{attr: color})
            if attr == 'bg':
                for child in widget.winfo_children():
                    try:
                        child.configure(bg=color)
                        if 'activebackground' in child.keys():
                            child.configure(activebackground=color)
                    except Exception:
                        pass
        except Exception:
            pass

    # ---------------- 候选行 ----------------
    def _build_candidate_row(self, i):
        # 行使用原生 tk 组件（无画布绘制层），滚动不产生拖尾；无勾选框，纯底色表达选中态
        C = self.C
        s = self.candidates[i]
        row_bg = C['card2'] if i in self.checked_candidates else C['card']
        row = tk.Frame(self.cand_list, bg=row_bg, cursor='hand2')
        row.pack(fill='x', padx=6, pady=1)
        name = tk.Label(row, text=short(s.name, 24), bg=row_bg, fg=C['text'], font=self.f_bold,
                        anchor='w', cursor='hand2')
        name.pack(side='left', padx=(10, 8), pady=4)
        meta = tk.Label(row, text=self._cand_meta_text(s), bg=row_bg, fg=C['muted'], font=self.f_tiny,
                        anchor='e', cursor='hand2')
        meta.pack(side='right', padx=(8, 10), pady=4)
        self.cand_rows[i] = row
        for w in (row, name, meta):
            w.bind('<Button-1>', lambda e, idx=i: self._cand_toggle(idx))
            w.bind('<Enter>', lambda e, idx=i, frm=row: self._row_enter(frm, idx))
            w.bind('<Leave>', lambda e, idx=i, frm=row: self._row_leave(frm, idx))
            w.bind('<Double-Button-1>', lambda e, idx=i: self._cand_detail(idx))
            w.bind('<Button-3>', lambda e, idx=i: self.show_candidate_menu(e, idx))

    def _cand_toggle(self, i):
        if i in self.checked_candidates:
            self.checked_candidates.discard(i)
        else:
            self.checked_candidates.add(i)
        self._cand_sync(i)

    def _cand_sync(self, i):
        v = i in self.checked_candidates
        row = self.cand_rows.get(i)
        if row is not None:
            self._set_row_color(row, self.C['card2'] if v else self.C['card'])
        self._update_action_buttons()
        self._refresh_count_label()

    def _row_enter(self, row, i):
        if i not in self.checked_candidates:
            self._set_row_color(row, self.C['hover'])

    def _row_leave(self, row, i):
        self._set_row_color(row, self.C['card2'] if i in self.checked_candidates else self.C['card'])

    def _refresh_count_label(self):
        shown = sum(1 for i in range(len(self.candidates)) if self._candidate_visible(i))
        total = len(self.candidates)
        self.cand_count.configure(text='共 {} 个{} · 已选 {}'.format(
            total, (' · 显示 {}'.format(shown) if shown != total else ''), len(self.checked_candidates)))

    # ---------------- 已导入行 ----------------
    def _build_imported_row(self, i, e):
        # 行使用原生 tk 组件（无画布绘制层），滚动不产生拖尾；无勾选框，纯底色表达选中态
        C = self.C
        row_bg = C['card2'] if i in self.checked_imported else C['card']
        row = tk.Frame(self.imp_list, bg=row_bg, cursor='hand2')
        row.pack(fill='x', padx=6, pady=1)
        name = tk.Label(row, text=short(e.get('name', ''), 24), bg=row_bg, fg=C['text'], font=self.f_bold,
                        anchor='w', cursor='hand2')
        name.pack(side='left', padx=(10, 8), pady=4)
        meta = tk.Label(row, text=self._imp_meta_text(e), bg=row_bg, fg=C['muted'], font=self.f_tiny,
                        anchor='e', cursor='hand2')
        meta.pack(side='right', padx=(8, 10), pady=4)
        self.imp_rows[i] = row
        for w in (row, name, meta):
            w.bind('<Button-1>', lambda ev, idx=i: self._imp_toggle(idx))
            w.bind('<Enter>', lambda ev, idx=i, frm=row: self._imp_enter(frm, idx))
            w.bind('<Leave>', lambda ev, idx=i, frm=row: self._imp_leave(frm, idx))
            w.bind('<Double-Button-1>', lambda ev, idx=i: self._imported_detail(idx))
            w.bind('<Button-3>', lambda ev, idx=i: self.show_imported_menu(ev, idx))

    def _imp_toggle(self, i):
        if i in self.checked_imported:
            self.checked_imported.discard(i)
        else:
            self.checked_imported.add(i)
        self._imp_sync(i)

    def _imp_sync(self, i):
        v = i in self.checked_imported
        row = self.imp_rows.get(i)
        if row is not None:
            self._set_row_color(row, self.C['card2'] if v else self.C['card'])
        self.imp_count.configure(text='共 {} 个 · 已选 {}'.format(len(self.entries), len(self.checked_imported)))

    def _imp_enter(self, row, i):
        if i not in self.checked_imported:
            self._set_row_color(row, self.C['hover'])

    def _imp_leave(self, row, i):
        self._set_row_color(row, self.C['card2'] if i in self.checked_imported else self.C['card'])

    # ---------------- 备份行 ----------------
    def _bk_toggle(self, name, row):
        if name in self.checked_backups:
            self.checked_backups.discard(name)
        else:
            self.checked_backups.add(name)
        self._bk_sync(name, row)

    def _bk_sync(self, name, row):
        self._set_row_color(row, self.C['card2'] if name in self.checked_backups else self.C['card'])

    # ---------------- 视图钩子 ----------------
    def _view_refresh_candidates(self):
        ctk, C = self.ctk, self.C
        for w in self.cand_list.winfo_children():
            w.destroy()
        self.cand_rows = {}
        self.checked_candidates = {i for i in self.checked_candidates if 0 <= i < len(self.candidates)}
        if not self.candidates:
            tk.Label(self.cand_list,
                     text='尚未选择音源文件夹\n\n点击上方「选择音源文件夹」，工具将自动遍历所有子文件夹\n并识别其中的 .js 音源脚本',
                     bg=C['card'], fg=C['faint'], font=self.f_small, justify='center').pack(pady=40)
        else:
            shown = 0
            for i in range(len(self.candidates)):
                if not self._candidate_visible(i):
                    continue
                shown += 1
                self._build_candidate_row(i)
            if shown == 0:
                tk.Label(self.cand_list, text='没有匹配「{}」的音源'.format(self.candidate_filter),
                         bg=C['card'], fg=C['faint'], font=self.f_small).pack(pady=24)
        self._refresh_count_label()
        self._update_action_buttons()

    def _view_refresh_imported(self):
        ctk, C = self.ctk, self.C
        for w in self.imp_list.winfo_children():
            w.destroy()
        self.imp_rows = {}
        self.checked_imported = {i for i in self.checked_imported if 0 <= i < len(self.entries)}
        if not self.entries:
            tk.Label(self.imp_list, text='暂无已导入音源', bg=C['card'], fg=C['faint'], font=self.f_small).pack(pady=40)
        else:
            for i, e in enumerate(self.entries):
                self._build_imported_row(i, e)
        self.imp_count.configure(text='共 {} 个 · 已选 {}'.format(len(self.entries), len(self.checked_imported)))

    def _view_refresh_backups(self):
        ctk, C = self.ctk, self.C
        for w in self.bk_list.winfo_children():
            w.destroy()
        self.bk_rows = {}
        files = self.backups.list_files()
        self.checked_backups = {n for n in self.checked_backups if any(f['name'] == n for f in files)}
        if not files:
            tk.Label(self.bk_list, text='暂无备份文件（每次写操作前会自动生成）',
                     bg=C['card'], fg=C['faint'], font=self.f_small).pack(pady=14)
            return
        for f in files:
            row_bg = C['card2'] if f['name'] in self.checked_backups else C['card']
            row = tk.Frame(self.bk_list, bg=row_bg, cursor='hand2')
            row.pack(fill='x', padx=4, pady=2)
            name_l = tk.Label(row, text=f['name'], bg=row_bg, fg=C['text'], font=self.f_small,
                              anchor='w', cursor='hand2')
            name_l.pack(side='left', padx=(14, 4), pady=5)
            meta_l = tk.Label(row, text='{:.1f} KB · {}'.format(f['size'] / 1024.0, f['mtime']),
                              bg=row_bg, fg=C['faint'], font=self.f_tiny, cursor='hand2')
            meta_l.pack(side='right', padx=10, pady=5)
            for w in (row, name_l, meta_l):
                w.bind('<Button-1>', lambda e, n=f['name'], frm=row: self._bk_toggle(n, frm))

    # ---------------- 订阅行 ----------------
    def _build_sub_row(self, i, sub):
        C = self.C
        is_current = sub.get('repo') == self._current_sub
        row_bg = C['card2'] if is_current else C['card']
        row = tk.Frame(self.sub_list, bg=row_bg, cursor='hand2')
        row.pack(fill='x', padx=6, pady=1)
        name_l = tk.Label(row, text=short(sub.get('repo', ''), 26), bg=row_bg, fg=C['text'],
                          font=self.f_bold, anchor='w', cursor='hand2')
        name_l.pack(side='left', padx=(10, 8), pady=4)
        tag = sub.get('last_tag')
        st_l = tk.Label(row, text=self._sub_meta_text(sub), bg=row_bg,
                        fg=C['green'] if tag else C['faint'], font=self.f_tiny, cursor='hand2')
        st_l.pack(side='right', padx=(8, 10), pady=4)
        self.sub_rows[i] = row
        for w in (row, name_l, st_l):
            w.bind('<Button-1>', lambda e, s=sub: self.do_show_subscription_sources(s))
            w.bind('<Double-Button-1>', lambda e, s=sub: self.do_update_subscription(s))
            w.bind('<Enter>', lambda e, frm=row, cur=is_current: self._sub_enter(frm, cur))
            w.bind('<Leave>', lambda e, frm=row, cur=is_current: self._sub_leave(frm, cur))
            w.bind('<Button-3>', lambda e, idx=i: self.show_sub_menu(e, idx))

    def _sub_enter(self, row, is_current):
        if not is_current:
            self._set_row_color(row, self.C['hover'])

    def _sub_leave(self, row, is_current):
        self._set_row_color(row, self.C['card2'] if is_current else self.C['card'])

    def _view_refresh_subscriptions(self):
        for w in self.sub_list.winfo_children():
            w.destroy()
        self.sub_rows = {}
        if not self.subscriptions:
            tk.Label(self.sub_list,
                     text='暂无订阅\n点「添加订阅」填入 GitHub 仓库（owner/repo）\n单击订阅可把其本地音源加载到「待导入音源」\n双击订阅立即下载并更新',
                     bg=self.C['card'], fg=self.C['faint'], font=self.f_small, justify='center').pack(pady=14)
            return
        for i, sub in enumerate(self.subscriptions):
            self._build_sub_row(i, sub)

    def _view_input(self, title, prompt, password=False):
        ctk, C = self.ctk, self.C
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(title)
        dlg.configure(fg_color=C['card'])
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        ctk.CTkLabel(dlg, text=prompt, wraplength=400, justify='left', font=self.f_base,
                     text_color=C['text']).pack(padx=22, pady=(18, 10), anchor='w')
        entry = ctk.CTkEntry(dlg, width=380, height=32, corner_radius=6, fg_color=C['field'],
                             border_color=C['border'], text_color=C['text'], font=self.f_small,
                             show='*' if password else '')
        entry.pack(padx=22, pady=(0, 12))
        btns = ctk.CTkFrame(dlg, fg_color='transparent')
        btns.pack(pady=(0, 16))
        result = {'val': None}

        def ok():
            result['val'] = entry.get().strip()
            dlg.destroy()

        entry.bind('<Return>', lambda e: ok())
        ctk.CTkButton(btns, text='取消', width=96, height=32, corner_radius=6, font=self.f_btn,
                      fg_color='transparent', border_width=1, border_color=C['border'],
                      text_color=C['muted'], hover_color=C['hover'], command=dlg.destroy).pack(side='left', padx=6)
        ctk.CTkButton(btns, text='确定', width=96, height=32, corner_radius=6, font=self.f_btn,
                      fg_color=C['accent'], hover_color=C['accent_hover'], text_color='#fffaf5', command=ok).pack(side='left', padx=6)
        try:
            dlg.update_idletasks()
            w = max(460, dlg.winfo_reqwidth() + 40)
            h = dlg.winfo_reqheight() + 16
            x = self.root.winfo_rootx() + max((self.root.winfo_width() - w) // 2, 0)
            y = self.root.winfo_rooty() + max((self.root.winfo_height() - h) // 2, 0)
            dlg.geometry('{}x{}+{}+{}'.format(w, h, x, y))
        except Exception:
            pass
        dlg.after(60, entry.focus_set)
        dlg.wait_window()
        return result['val']

    # ---------------- 配置窗口 ----------------
    def _view_apply_backup_visible(self):
        try:
            if self.settings.get('backup_enabled', True):
                self._bk_card.grid()
            else:
                self._bk_card.grid_remove()
        except Exception:
            pass

    def _view_apply_log_visible(self):
        try:
            show = self.settings.get('log_enabled', True) and self.settings.get('log_window', True)
            if show:
                self._lg_card.grid()
            else:
                self._lg_card.grid_remove()
        except Exception:
            pass

    def _view_refresh_settings_row(self):
        try:
            self.dl_var.set(self.DL_LABELS.get(self.settings.get('downloader', 'auto'), '自动'))
        except Exception:
            pass
        try:
            if hasattr(self, 'cfg_dl_var'):
                self.cfg_dl_var.set(self.DL_LABELS.get(self.settings.get('downloader', 'auto'), '自动'))
            if hasattr(self, 'cfg_dl_status'):
                self.cfg_dl_status.configure(text=self._downloader_status_text())
        except Exception:
            pass

    def do_open_settings(self):
        ctk, C = self.ctk, self.C
        if self._settings_win is not None:
            try:
                if self._settings_win.winfo_exists():
                    self._settings_win.lift()
                    return
            except Exception:
                pass
        win = ctk.CTkToplevel(self.root)
        self._settings_win = win
        win.title('设置')
        win.configure(fg_color=C['bg'])
        win.resizable(False, False)
        win.transient(self.root)
        win.protocol('WM_DELETE_WINDOW', self._on_settings_close)
        win.grid_columnconfigure(0, weight=1)

        def sec(title, row):
            f = ctk.CTkFrame(win, fg_color=C['card'], corner_radius=8)
            f.grid(row=row, column=0, sticky='ew', padx=16, pady=(10, 0))
            f.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(f, text=title, font=self.f_card, text_color=C['text']).grid(
                row=0, column=0, columnspan=3, sticky='w', padx=14, pady=(10, 4))
            return f

        def wlab(f, r, text, col=0, span=1):
            ctk.CTkLabel(f, text=text, font=self.f_small, text_color=C['text'], anchor='w').grid(
                row=r, column=col, columnspan=span, sticky='w', padx=(14, 8), pady=4)

        def wsub(f, r, text):
            ctk.CTkLabel(f, text=text, font=self.f_tiny, text_color=C['faint'], anchor='w').grid(
                row=r, column=1, columnspan=2, sticky='w', padx=14, pady=(0, 4))

        def wentry(f, r, value, on_change, width=30):
            e = tk.Entry(f, bg=C['field'], fg=C['text'], insertbackground=C['text'],
                         relief='flat', highlightthickness=1, highlightbackground=C['border'],
                         highlightcolor=C['accent'], font=self.f_small, width=width)
            e.grid(row=r, column=1, sticky='ew', padx=(0, 8), pady=4)
            e.insert(0, value)
            e.bind('<Return>', lambda ev: on_change(e.get()))
            e.bind('<FocusOut>', lambda ev: on_change(e.get()))
            return e

        def wcheck(f, r, var, label, on_toggle):
            WebCheck(f, variable=var, command=on_toggle).grid(row=r, column=0, padx=(14, 4), pady=4)
            wlab(f, r, label, 1)

        # ---- 一、备份配置 ----
        f1 = sec('一、备份配置', 0)
        self.cfg_backup_var = tk.BooleanVar(value=self.settings.get('backup_enabled', True))
        wcheck(f1, 1, self.cfg_backup_var, '自动备份（每次写操作前备份；关闭后隐藏备份模块）',
               lambda: self.do_set_backup_enabled(self.cfg_backup_var.get()))
        wlab(f1, 2, '备份文件夹', 0)
        self.cfg_backup_entry = wentry(f1, 2, effective_backup_dir(self.settings),
                                       self.do_set_backup_dir)
        self._btn(f1, '浏览…', lambda: self._pick_dir_to(self.cfg_backup_entry, self.do_set_backup_dir),
                  width=64).grid(row=2, column=2, padx=(0, 14), pady=4)
        wsub(f1, 3, '更改目录时可将旧备份迁移到新位置')

        # ---- 二、订阅配置 ----
        f2 = sec('二、订阅配置', 1)
        wlab(f2, 1, '下载目录', 0)
        self.cfg_dl_entry = wentry(f2, 1, effective_download_dir(self.settings),
                                   self.do_set_download_dir)
        self._btn(f2, '浏览…', lambda: self._pick_dir_to(self.cfg_dl_entry, self.do_set_download_dir),
                  width=64).grid(row=1, column=2, padx=(0, 14), pady=4)
        wsub(f2, 2, '每个订阅存放于 下载目录/<仓库名>/ 子文件夹；zip 自动解压，旧版本归档到 history/')
        wlab(f2, 3, '下载方式', 0)
        self.cfg_dl_var = tk.StringVar(value=self.DL_LABELS.get(self.settings.get('downloader', 'auto'), '自动'))
        self.cfg_dl_menu = ctk.CTkOptionMenu(f2, values=list(self.DL_LABELS.values()),
                                             variable=self.cfg_dl_var, width=110, height=28,
                                             font=self.f_small, dropdown_font=self.f_small,
                                             fg_color=C['field'], button_color=C['border'],
                                             button_hover_color=C['hover'], text_color=C['text'],
                                             dropdown_fg_color=C['card'], dropdown_hover_color=C['card2'],
                                             dropdown_text_color=C['text'],
                                             command=self._on_downloader_pick)
        self.cfg_dl_menu.grid(row=3, column=1, sticky='w', padx=(0, 8), pady=4)
        self.cfg_dl_status = ctk.CTkLabel(f2, text=self._downloader_status_text(), font=self.f_tiny,
                                          text_color=C['faint'], anchor='w')
        self.cfg_dl_status.grid(row=3, column=2, sticky='w', padx=(0, 10), pady=4)
        self._btn(f2, '测试 ABDM', self.do_test_abdm, width=84).grid(row=3, column=3, padx=(0, 8), pady=4)
        self._btn(f2, '指定 ABDM…', self.do_pick_abdm, width=92).grid(row=3, column=4, padx=(0, 14), pady=4)
        self.cfg_hist_var = tk.BooleanVar(value=self.settings.get('keep_history', True))
        wcheck(f2, 4, self.cfg_hist_var, '保留历史版本（关闭后更新时直接清除旧版本）',
               lambda: self.do_set_keep_history(self.cfg_hist_var.get()))
        wlab(f2, 5, '已有订阅', 0)
        self.cfg_sublist = tk.Listbox(f2, height=3, bg=C['field'], fg=C['text'], relief='flat',
                                      highlightthickness=1, highlightbackground=C['border'],
                                      font=self.f_small, selectbackground=C['card2'],
                                      selectforeground=C['text'])
        self.cfg_sublist.grid(row=5, column=1, columnspan=2, sticky='ew', padx=(0, 14), pady=4)
        for s in self.subscriptions:
            self.cfg_sublist.insert('end', s.get('repo', ''))
        self._btn(f2, '打开文件夹', self._open_cfg_sub_dir, width=84).grid(
            row=6, column=1, sticky='w', padx=(0, 8), pady=(0, 10))
        self._btn(f2, '删除订阅', self._delete_cfg_sub, width=84).grid(
            row=6, column=2, sticky='w', padx=(0, 14), pady=(0, 10))

        # ---- 三、日志配置 ----
        f3 = sec('三、日志配置', 2)
        self.cfg_log_var = tk.BooleanVar(value=self.settings.get('log_enabled', True))
        self.cfg_log_check = WebCheck(f3, variable=self.cfg_log_var,
                                      command=lambda: self.do_set_log_enabled(self.cfg_log_var.get()))
        self.cfg_log_check.grid(row=1, column=0, padx=(14, 4), pady=4)
        wlab(f3, 1, '记录日志（写入 config/logs/app.log）', 1)
        self.cfg_logwin_var = tk.BooleanVar(
            value=self.settings.get('log_enabled', True) and self.settings.get('log_window', True))
        self.cfg_logwin_check = WebCheck(f3, variable=self.cfg_logwin_var,
                                         command=lambda: self.do_set_log_window(self.cfg_logwin_var.get()))
        self.cfg_logwin_check.grid(row=2, column=0, padx=(14, 4), pady=4)
        self.cfg_logwin_label = ctk.CTkLabel(f3, text='显示日志窗口（需先开启记录日志）', font=self.f_small,
                                             text_color=C['text'], anchor='w')
        self.cfg_logwin_label.grid(row=2, column=1, columnspan=2, sticky='w', padx=(14, 8), pady=4)
        self._view_refresh_cfg_logwin()

        bottom_row = ctk.CTkFrame(win, fg_color='transparent')
        bottom_row.grid(row=3, column=0, sticky='e', padx=16, pady=12)
        self._btn(bottom_row, '关闭', self._on_settings_close, width=88).pack(side='left')
        try:
            win.update_idletasks()
            w = max(620, win.winfo_reqwidth() + 30)
            h = win.winfo_reqheight() + 12
            x = self.root.winfo_rootx() + max((self.root.winfo_width() - w) // 2, 0)
            y = self.root.winfo_rooty() + max((self.root.winfo_height() - h) // 2, 0)
            win.geometry('{}x{}+{}+{}'.format(w, h, x, y))
        except Exception:
            pass

    def _view_rebalance_bottom(self):
        # 隐藏某个底部模块时重排网格，让剩余卡片自动瓜分全部宽度
        try:
            show_bk = self.settings.get('backup_enabled', True)
            show_lg = self.settings.get('log_enabled', True) and self.settings.get('log_window', True)
            cards = []
            weights = []
            if show_bk:
                cards.append(self._bk_card)
                weights.append(2)
            cards.append(self._sub_card)
            weights.append(3)
            if show_lg:
                cards.append(self._lg_card)
                weights.append(3)
            for i, card in enumerate(cards):
                left = 0 if i == 0 else 6
                right = 0 if i == len(cards) - 1 else 6
                card.grid(row=0, column=i, sticky='nsew', padx=(left, right))
            for i in range(3):
                w = weights[i] if i < len(weights) else 0
                # 权重为 0 的列退出 uniform 组，否则 Tk 会按 weight=1 分走宽度
                self._bottom.grid_columnconfigure(i, weight=w, uniform=('bot' if w > 0 else ''))
        except Exception:
            pass

    def _view_refresh_cfg_logwin(self):
        # 记录日志关闭时：显示日志窗口自动关闭并置灰；开启时恢复可点
        C = self.C
        try:
            enabled = self.settings.get('log_enabled', True)
            if hasattr(self, 'cfg_logwin_var'):
                self.cfg_logwin_var.set(enabled and self.settings.get('log_window', True))
            if hasattr(self, 'cfg_logwin_check'):
                self.cfg_logwin_check.set_state(enabled)
            if hasattr(self, 'cfg_logwin_label'):
                self.cfg_logwin_label.configure(text_color=C['text'] if enabled else C['faint'])
        except Exception:
            pass

    def _view_log(self, text, level='info'):
        try:
            self.logbox.configure(state='normal')
            self.logbox.insert('end', text + '\n', level)
            self.logbox.see('end')
            self.logbox.configure(state='disabled')
        except Exception:
            pass

    def _view_set_status(self, text):
        self.status_var.set(text)

    def _view_confirm(self, title, message, danger=False):
        return self._dialog(title, message, danger=danger, confirm=True)

    def _view_info(self, title, message):
        self._dialog(title, message, danger=False, confirm=False)

    def _dialog(self, title, message, danger=False, confirm=True):
        ctk, C = self.ctk, self.C
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(title)
        dlg.configure(fg_color=C['card'])
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        ctk.CTkLabel(dlg, text=message, wraplength=440, justify='left', font=self.f_base,
                     text_color=C['text']).pack(padx=22, pady=(20, 14), anchor='w')
        btns = ctk.CTkFrame(dlg, fg_color='transparent')
        btns.pack(pady=(0, 18))
        result = {'ok': False}
        if confirm:
            def ok():
                result['ok'] = True
                dlg.destroy()
            ctk.CTkButton(btns, text='取消', width=96, height=32, corner_radius=6, font=self.f_btn,
                          fg_color='transparent', border_width=1, border_color=C['border'],
                          text_color=C['muted'], hover_color=C['hover'], command=dlg.destroy).pack(side='left', padx=6)
            ok_fg = C['danger'] if danger else C['accent']
            ok_hover = '#ad4f3e' if danger else C['accent_hover']
            ctk.CTkButton(btns, text='确定', width=96, height=32, corner_radius=6, font=self.f_btn,
                          fg_color=ok_fg, hover_color=ok_hover, text_color='#fffaf5', command=ok).pack(side='left', padx=6)
        else:
            ctk.CTkButton(btns, text='知道了', width=96, height=32, corner_radius=6, font=self.f_btn,
                          fg_color=C['accent'], hover_color=C['accent_hover'], text_color='#fffaf5',
                          command=dlg.destroy).pack(side='left', padx=6)
        dlg.protocol('WM_DELETE_WINDOW', dlg.destroy)
        try:
            dlg.after(10, lambda: dlg.iconphoto(False, self.icon))
        except Exception:
            pass
        # 根据内容自适应尺寸，保证按钮始终可见
        try:
            dlg.update_idletasks()
            w = max(500, dlg.winfo_reqwidth() + 40)
            h = dlg.winfo_reqheight() + 16
            x = self.root.winfo_rootx() + max((self.root.winfo_width() - w) // 2, 0)
            y = self.root.winfo_rooty() + max((self.root.winfo_height() - h) // 2, 0)
            dlg.geometry('{}x{}+{}+{}'.format(w, h, x, y))
        except Exception:
            pass
        dlg.wait_window()
        return result['ok']

    def _view_show_detail(self, title, text):
        ctk, C = self.ctk, self.C
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(title)
        dlg.configure(fg_color=C['card'])
        dlg.geometry('680x480')
        dlg.transient(self.root)
        try:
            self.root.update_idletasks()
            x = self.root.winfo_rootx() + max((self.root.winfo_width() - 680) // 2, 0)
            y = self.root.winfo_rooty() + max((self.root.winfo_height() - 480) // 2, 0)
            dlg.geometry('680x480+{}+{}'.format(x, y))
        except Exception:
            pass
        dlg.grid_columnconfigure(0, weight=1)
        dlg.grid_rowconfigure(0, weight=1)
        tb = ctk.CTkTextbox(dlg, fg_color=C['field'], corner_radius=6, font=self.f_small, wrap='word')
        tb.grid(row=0, column=0, sticky='nsew', padx=12, pady=(12, 4))
        tb.insert('1.0', text)
        tb.configure(state='disabled')
        self._btn(dlg, '关闭', dlg.destroy, width=88).grid(row=1, column=0, pady=(0, 12))
        try:
            dlg.after(10, lambda: dlg.iconphoto(False, self.icon))
        except Exception:
            pass
    def _view_ask_folder(self):
        return filedialog.askdirectory(title='选择包含音源脚本的文件夹（将遍历所有子文件夹）',
                                       parent=self.root, initialdir=self.last_folder)

    def _view_ask_file(self):
        init = os.path.dirname(self.user_api_path) if self.user_api_path else None
        if init and not os.path.isdir(init):
            init = None
        return filedialog.askopenfilename(title='选择 user_api.json', parent=self.root,
                                          filetypes=[('JSON 文件', '*.json'), ('所有文件', '*.*')], initialdir=init)


# ---------------------------------------------------------------- tkinter / ttk 回退界面
class TtkApp(BaseApp):
    def __init__(self, user_api_path=None, backup_dir=None, auto_confirm=False, hidden=False):
        self.C = PALETTE
        self.animations = not hidden
        self.settings = load_settings()
        set_mirror(self.settings['mirror'])
        self.use_idm = self.settings['use_idm']
        self.idm_path = find_idm_path()
        self.abdm_path = self.settings.get('abdm_path') or find_abdm_path()
        self.root = tk.Tk()
        if hidden:
            self.root.withdraw()
        self.root.title(APP_TITLE)
        self.root.geometry('1220x800')
        self.root.minsize(1100, 720)
        self.root.configure(bg=self.C['bg'])
        self.icon = _make_icon()
        try:
            self.root.iconphoto(True, self.icon)
        except Exception:
            pass
        self.path_label = None
        self.folder_label = None
        self._init_style()
        self._build()
        super().__init__(user_api_path=user_api_path, backup_dir=backup_dir, auto_confirm=auto_confirm)
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

    def _init_style(self):
        C = self.C
        F = FONT_FAMILY
        s = ttk.Style(self.root)
        try:
            s.theme_use('clam')
        except Exception:
            pass
        s.configure('.', background=C['bg'], foreground=C['text'], fieldbackground=C['field'],
                    bordercolor=C['border'], lightcolor=C['border'], darkcolor=C['border'],
                    troughcolor=C['field'], font=(F, 10))
        s.configure('TFrame', background=C['bg'])
        s.configure('Card.TFrame', background=C['card'])
        s.configure('TLabel', background=C['bg'], foreground=C['text'])
        s.configure('Card.TLabel', background=C['card'], foreground=C['text'])
        s.configure('CardTitle.TLabel', background=C['card'], foreground=C['text'], font=(F, 13, 'bold'))
        s.configure('Muted.TLabel', background=C['card'], foreground=C['muted'], font=(F, 9))
        s.configure('Status.TLabel', background=C['bg'], foreground=C['faint'], font=(F, 9))
        s.configure('TButton', background=C['card2'], foreground=C['text'], borderwidth=0,
                    focusthickness=0, padding=(10, 5), font=(F, 10))
        s.map('TButton', background=[('active', C['hover']), ('pressed', C['card2'])],
              foreground=[('active', C['text'])])
        s.configure('Accent.TButton', background=C['accent'], foreground='#fffaf5', borderwidth=0,
                    focusthickness=0, padding=(12, 5), font=(F, 10))
        s.map('Accent.TButton', background=[('active', C['accent_hover']), ('pressed', C['accent'])],
              foreground=[('active', '#fffaf5')])
        s.configure('Danger.TButton', background=C['danger'], foreground='#fffaf5', borderwidth=0,
                    focusthickness=0, padding=(12, 5), font=(F, 10))
        s.map('Danger.TButton', background=[('active', '#e56a6f')], foreground=[('active', '#fffaf5')])
        s.configure('TEntry', fieldbackground=C['field'], foreground=C['text'], insertcolor=C['text'],
                    bordercolor=C['border'], lightcolor=C['border'], darkcolor=C['border'], padding=5)
        s.configure('Treeview', background=C['field'], fieldbackground=C['field'], foreground=C['text'],
                    rowheight=26, borderwidth=0, font=(F, 10))
        s.map('Treeview', background=[('selected', C['accent'])], foreground=[('selected', '#fffaf5')])
        s.configure('Treeview.Heading', background=C['card2'], foreground=C['text'], borderwidth=0,
                    font=(F, 10, 'bold'), padding=4)
        s.map('Treeview.Heading', background=[('active', C['hover'])])
        s.configure('TRadiobutton', background=C['card'], foreground=C['text'], font=(F, 10))
        s.map('TRadiobutton', background=[('active', C['card'])], indicatorcolor=[('selected', C['accent'])])
        s.configure('TScrollbar', background=C['card2'], troughcolor=C['bg'], bordercolor=C['bg'],
                    arrowcolor=C['muted'])
        s.map('TScrollbar', background=[('active', C['hover'])])

    def _build(self):
        C = self.C
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(self.root, style='Card.TFrame', padding=(16, 12))
        header.grid(row=0, column=0, sticky='ew', padx=12, pady=(10, 4))
        header.grid_columnconfigure(1, weight=1)
        ttk.Label(header, text='LX Music 音源一键导入 / 更新工具', style='CardTitle.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(header, text='洛雪音乐桌面版 · 自定义音源批量导入、更新、备份与清除', style='Muted.TLabel').grid(row=1, column=0, sticky='w')
        self.path_label = ttk.Label(header, text='', style='Muted.TLabel')
        self.path_label.grid(row=0, column=1, rowspan=2, sticky='e', padx=(8, 10))
        ttk.Button(header, text='⚙', command=self.do_open_settings, width=4).grid(row=0, column=2, rowspan=2, sticky='e', padx=(0, 4))
        ttk.Button(header, text='重新定位', command=self.do_relocate).grid(row=0, column=3, rowspan=2, sticky='e', padx=(0, 4))
        ttk.Button(header, text='打开数据目录', command=self.do_open_data_dir).grid(row=0, column=4, rowspan=2, sticky='e', padx=(4, 0))

        main = ttk.Frame(self.root)
        main.grid(row=1, column=0, sticky='nsew', padx=12, pady=4)
        main.grid_columnconfigure((0, 1), weight=1, uniform='col')
        main.grid_rowconfigure(0, weight=1)

        # ----- 左：待导入 -----
        left = ttk.Frame(main, style='Card.TFrame', padding=12)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(3, weight=1)
        ttk.Label(left, text='待导入音源', style='CardTitle.TLabel').grid(row=0, column=0, sticky='w')
        self.folder_label = ttk.Label(left, text='尚未选择文件夹', style='Muted.TLabel')
        self.folder_label.grid(row=0, column=1, sticky='e')
        bar = ttk.Frame(left, style='Card.TFrame')
        bar.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(6, 2))
        ttk.Button(bar, text='选择音源文件夹', style='Accent.TButton', command=self.do_scan_folder).pack(side='left', padx=(0, 4))
        ttk.Button(bar, text='全选', command=lambda: self.do_select_all_candidates(True)).pack(side='left', padx=2)
        ttk.Button(bar, text='全不选', command=lambda: self.do_select_all_candidates(False)).pack(side='left', padx=2)
        ttk.Button(bar, text='移除所选', command=self.do_remove_candidates).pack(side='left', padx=2)
        ttk.Button(bar, text='清空列表', command=self.do_clear_candidates).pack(side='left', padx=2)
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', lambda *a: self._on_search())
        ttk.Entry(left, textvariable=self.search_var).grid(row=2, column=0, columnspan=2, sticky='ew', pady=(2, 4))
        self.cand_tree = ttk.Treeview(left, columns=('chk', 'name', 'meta'), show='headings',
                                      selectmode='none')
        for col, txt, width, anchor in (('chk', '选', 36, 'center'), ('name', '音源名称', 210, 'w'),
                                        ('meta', '版本 · 作者 · 路径', 430, 'w')):
            self.cand_tree.heading(col, text=txt)
            self.cand_tree.column(col, width=width, anchor=anchor, stretch=(col == 'meta'))
        self.cand_tree.tag_configure('checked', background=C['card2'], foreground=C['text'])
        self.cand_tree.grid(row=3, column=0, sticky='nsew', pady=2)
        self.cand_tree.bind('<Button-1>', self._on_cand_click)
        self.cand_tree.bind('<Double-1>', self._on_cand_double)
        self.cand_tree.bind('<Button-3>', self._on_cand_menu)
        vsb = ttk.Scrollbar(left, orient='vertical', command=self.cand_tree.yview)
        self.cand_tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=3, column=1, sticky='ns')
        mrow = ttk.Frame(left, style='Card.TFrame')
        mrow.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(8, 0))
        ttk.Label(mrow, text='导入模式：', style='Card.TLabel').pack(side='left')
        self.mode_var = tk.StringVar(value=MODE_ADD_LABEL)
        ttk.Radiobutton(mrow, text=MODE_ADD_LABEL, value=MODE_ADD_LABEL, variable=self.mode_var,
                        command=lambda: self._set_mode(self.mode_var.get())).pack(side='left', padx=6)
        ttk.Radiobutton(mrow, text=MODE_UPDATE_LABEL, value=MODE_UPDATE_LABEL, variable=self.mode_var,
                        command=lambda: self._set_mode(self.mode_var.get())).pack(side='left', padx=6)
        arow = ttk.Frame(left, style='Card.TFrame')
        arow.grid(row=5, column=0, columnspan=2, sticky='ew', pady=(8, 2))
        self.btn_import_sel = ttk.Button(arow, text='导入所选', style='Accent.TButton', command=self.do_import)
        self.btn_import_sel.pack(side='left', padx=(0, 6))
        self.btn_import_all = ttk.Button(arow, text='一键全部导入', command=lambda: self.do_import(all_selected=True))
        self.btn_import_all.pack(side='left')
        self.cand_count = ttk.Label(arow, text='', style='Muted.TLabel')
        self.cand_count.pack(side='right')
        ttk.Label(left, text='提示：点击行切换勾选；全选作用于当前显示项；「一键全部」作用于全部待导入音源；双击查看详情',
                  style='Muted.TLabel').grid(row=6, column=0, columnspan=2, sticky='w', pady=(2, 0))

        # ----- 右：已导入 -----
        right = ttk.Frame(main, style='Card.TFrame', padding=12)
        right.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        rhead = ttk.Frame(right, style='Card.TFrame')
        rhead.grid(row=0, column=0, sticky='ew')
        rhead.grid_columnconfigure(1, weight=1)
        ttk.Label(rhead, text='已导入音源', style='CardTitle.TLabel').grid(row=0, column=0, sticky='w')
        self.imp_count = ttk.Label(rhead, text='', style='Muted.TLabel')
        self.imp_count.grid(row=0, column=1, sticky='e', padx=(8, 6))
        ttk.Button(rhead, text='刷新', command=self._view_refresh_imported).grid(row=0, column=2, sticky='e')
        self.imp_tree = ttk.Treeview(right, columns=('name', 'meta'), show='headings',
                                     selectmode='extended')
        for col, txt, width in (('name', '名称', 210), ('meta', '版本 · 作者 · 描述', 430)):
            self.imp_tree.heading(col, text=txt)
            self.imp_tree.column(col, width=width, anchor='w', stretch=(col == 'meta'))
        self.imp_tree.grid(row=1, column=0, sticky='nsew', pady=(4, 2))
        self.imp_tree.bind('<<TreeviewSelect>>', self._on_imp_select)
        self.imp_tree.bind('<Double-1>', self._on_imp_double)
        self.imp_tree.bind('<Button-3>', self._on_imp_menu)
        vsb2 = ttk.Scrollbar(right, orient='vertical', command=self.imp_tree.yview)
        self.imp_tree.configure(yscrollcommand=vsb2.set)
        vsb2.grid(row=1, column=1, sticky='ns')
        arow2 = ttk.Frame(right, style='Card.TFrame')
        arow2.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(8, 0))
        ttk.Button(arow2, text='删除所选', command=self.do_delete_imported).pack(side='left', padx=(0, 6))
        ttk.Button(arow2, text='一键清除全部', style='Danger.TButton', command=self.do_clear_imported).pack(side='left')
        ttk.Label(arow2, text='Ctrl/Shift 多选；双击查看详情', style='Muted.TLabel').pack(side='right')
        ttk.Label(right, text='提示：修改 user_api.json 后需重启 LX Music 桌面版才会生效',
                  style='Muted.TLabel').grid(row=3, column=0, columnspan=2, sticky='w', pady=(2, 0))

        # ----- 底部：备份 + 订阅 + 日志 -----
        bottom = ttk.Frame(self.root)
        bottom.grid(row=2, column=0, sticky='ew', padx=12, pady=(4, 2))
        bottom.grid_columnconfigure(0, weight=2, uniform='bot')
        bottom.grid_columnconfigure(1, weight=3, uniform='bot')
        bottom.grid_columnconfigure(2, weight=3, uniform='bot')
        self._bottom = bottom
        bk = ttk.Frame(bottom, style='Card.TFrame', padding=12)
        bk.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        self._bk_card = bk
        bk.grid_columnconfigure(0, weight=1)
        bhead = ttk.Frame(bk, style='Card.TFrame')
        bhead.grid(row=0, column=0, sticky='ew')
        bhead.grid_columnconfigure(1, weight=1)
        ttk.Label(bhead, text='备份文件', style='CardTitle.TLabel').grid(row=0, column=0, sticky='w')
        bbtns = ttk.Frame(bhead, style='Card.TFrame')
        bbtns.grid(row=0, column=1, sticky='e')
        ttk.Button(bbtns, text='生成备份', command=self.do_backup).pack(side='left', padx=2)
        ttk.Button(bbtns, text='还原所选', command=self.do_restore_backup).pack(side='left', padx=2)
        ttk.Button(bbtns, text='打开文件夹', command=self.do_open_backup_dir).pack(side='left', padx=2)
        ttk.Button(bbtns, text='删除所选', command=self.do_delete_backups).pack(side='left', padx=2)
        ttk.Button(bbtns, text='清空备份', command=self.do_clear_backups).pack(side='left', padx=2)
        self.bk_box = tk.Listbox(bk, bg=C['field'], fg=C['text'], selectbackground=C['accent'],
                                 selectforeground='#fffaf5', relief='flat', highlightthickness=0,
                                 font=(FONT_FAMILY, 9), height=5, selectmode='extended', exportselection=False)
        self.bk_box.grid(row=1, column=0, sticky='ew', pady=(6, 0))
        self.bk_box.bind('<<ListboxSelect>>', self._on_bk_select)
        sub = ttk.Frame(bottom, style='Card.TFrame', padding=12)
        sub.grid(row=0, column=1, sticky='nsew', padx=(5, 5))
        sub.grid_columnconfigure(0, weight=1)
        shead = ttk.Frame(sub, style='Card.TFrame')
        shead.grid(row=0, column=0, sticky='ew')
        shead.grid_columnconfigure(1, weight=1)
        ttk.Label(shead, text='订阅更新', style='CardTitle.TLabel').grid(row=0, column=0, sticky='w')
        sbtns = ttk.Frame(shead, style='Card.TFrame')
        sbtns.grid(row=0, column=1, sticky='e')
        ttk.Button(sbtns, text='添加订阅', style='Accent.TButton', command=self.do_add_subscription).pack(side='left', padx=2)
        ttk.Button(sbtns, text='检查更新', command=self.do_check_subscriptions).pack(side='left', padx=2)
        ttk.Button(sbtns, text='一键更新', command=self.do_update_all_subscriptions).pack(side='left', padx=2)
        ttk.Button(sbtns, text='打开目录', command=self.do_open_download_dir).pack(side='left', padx=2)
        self.sub_tree = ttk.Treeview(sub, columns=('repo', 'st'), show='headings', height=5, selectmode='extended')
        self.sub_tree.heading('repo', text='仓库')
        self.sub_tree.heading('st', text='来源 · 版本')
        self.sub_tree.column('repo', width=170, anchor='w')
        self.sub_tree.column('st', width=90, anchor='w')
        self.sub_tree.grid(row=1, column=0, sticky='ew', pady=(6, 0))
        self.sub_tree.bind('<Button-1>', self._on_sub_click)
        self.sub_tree.bind('<Double-1>', self._on_sub_double)
        self.sub_tree.bind('<Button-3>', self._on_sub_menu)
        vsbs = ttk.Scrollbar(sub, orient='vertical', command=self.sub_tree.yview)
        self.sub_tree.configure(yscrollcommand=vsbs.set)
        vsbs.grid(row=1, column=1, sticky='ns', pady=(6, 0))
        setrow = ttk.Frame(sub, style='Card.TFrame')
        setrow.grid(row=2, column=0, columnspan=2, sticky='ew', padx=14, pady=(6, 0))
        ttk.Label(setrow, text='镜像', style='Muted.TLabel').pack(side='left')
        self.mirror_entry = ttk.Entry(setrow, width=16)
        self.mirror_entry.pack(side='left', padx=6)
        self.mirror_entry.insert(0, self.settings['mirror'])
        self._setup_placeholder(self.mirror_entry, MIRROR_PLACEHOLDER)
        self.mirror_entry.bind('<Return>', lambda e: self.do_set_mirror(self.mirror_entry.get()))
        self.mirror_entry.bind('<FocusOut>', lambda e: self.do_set_mirror(self.mirror_entry.get()))
        self.mirror_combo = ttk.Combobox(setrow, values=['直连', 'gh-proxy.com', 'ghfast.top', 'ghproxy.net', 'gh.api.99988866.xyz'],
                                         width=12, state='readonly')
        self.mirror_combo.bind('<<ComboboxSelected>>', lambda e: self._on_mirror_preset(self.mirror_combo.get()))
        self.mirror_combo.pack(side='left', padx=6)
        ttk.Label(setrow, text='下载', style='Muted.TLabel').pack(side='left', padx=(10, 4))
        self.dl_var = tk.StringVar(value=self.DL_LABELS.get(self.settings.get('downloader', 'auto'), '自动'))
        self.dl_box = ttk.Combobox(setrow, textvariable=self.dl_var, values=list(self.DL_LABELS.values()),
                                   state='readonly', width=6)
        self.dl_box.pack(side='left', padx=(0, 6))
        self.dl_box.bind('<<ComboboxSelected>>', lambda e: self._on_downloader_pick(self.dl_var.get()))

        lg = ttk.Frame(bottom, style='Card.TFrame', padding=12)
        lg.grid(row=0, column=2, sticky='nsew', padx=(5, 0))
        self._lg_card = lg
        lg.grid_columnconfigure(0, weight=1)
        lg.grid_rowconfigure(1, weight=1)
        lhead = ttk.Frame(lg, style='Card.TFrame')
        lhead.grid(row=0, column=0, sticky='ew')
        lhead.grid_columnconfigure(1, weight=1)
        ttk.Label(lhead, text='运行日志', style='CardTitle.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Button(lhead, text='清空日志', command=self.do_clear_log).grid(row=0, column=1, sticky='e')
        self.logbox = tk.Text(lg, bg=C['field'], fg=C['text'], insertbackground=C['text'], relief='flat',
                              height=6, font=(FONT_FAMILY, 9), wrap='word', state='disabled')
        self.logbox.grid(row=1, column=0, sticky='nsew', pady=(6, 0))
        for tag, color in LOG_COLORS.items():
            self.logbox.tag_config(tag, foreground=color)
        vsb3 = ttk.Scrollbar(lg, orient='vertical', command=self.logbox.yview)
        self.logbox.configure(yscrollcommand=vsb3.set)
        vsb3.grid(row=1, column=1, sticky='ns', pady=(6, 0))

        status = ttk.Frame(self.root)
        status.grid(row=3, column=0, sticky='ew', padx=12, pady=(0, 8))
        status.grid_columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value='')
        ttk.Label(status, textvariable=self.status_var, style='Status.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(status, text='所有写操作前自动备份；修改后需重启 LX Music 生效',
                  style='Status.TLabel').grid(row=0, column=1, sticky='e')

    # ---------------- 事件 ----------------
    def _on_cand_click(self, event):
        row = self.cand_tree.identify_row(event.y)
        if not row:
            return
        i = int(row)
        if i in self.checked_candidates:
            self.checked_candidates.discard(i)
        else:
            self.checked_candidates.add(i)
        self._view_refresh_candidates()

    def _on_cand_double(self, event):
        row = self.cand_tree.identify_row(event.y)
        if row:
            self._cand_detail(int(row))

    def _on_imp_select(self, event=None):
        self.checked_imported = {int(i) for i in self.imp_tree.selection()}
        self.imp_count.configure(text='共 {} 个 · 已选 {}'.format(len(self.entries), len(self.checked_imported)))

    def _on_imp_double(self, event):
        row = self.imp_tree.identify_row(event.y)
        if row:
            self._imported_detail(int(row))

    def _on_bk_select(self, event=None):
        self.checked_backups = set()
        for i in self.bk_box.curselection():
            self.checked_backups.add(self.bk_box.get(i))

    # ---------------- 视图钩子 ----------------
    def _view_refresh_candidates(self):
        tree = self.cand_tree
        tree.delete(*tree.get_children())
        self.checked_candidates = {i for i in self.checked_candidates if 0 <= i < len(self.candidates)}
        shown = 0
        for i, s in enumerate(self.candidates):
            if not self._candidate_visible(i):
                continue
            shown += 1
            chk = '☑' if i in self.checked_candidates else '☐'
            tree.insert('', 'end', iid=str(i),
                        values=(chk, short(s.name, 20), self._cand_meta_text(s)),
                        tags=(('checked',) if i in self.checked_candidates else ()))
        self.cand_count.configure(text='共 {} 个 · 显示 {} · 已选 {}'.format(
            len(self.candidates), shown, len(self.checked_candidates)))
        self._update_action_buttons()

    def _view_refresh_imported(self):
        tree = self.imp_tree
        tree.delete(*tree.get_children())
        for i, e in enumerate(self.entries):
            tree.insert('', 'end', iid=str(i),
                        values=(short(e.get('name', ''), 22), self._imp_meta_text(e)))
        self.checked_imported = {i for i in self.checked_imported if 0 <= i < len(self.entries)}
        for i in self.checked_imported:
            if tree.exists(str(i)):
                tree.selection_add(str(i))
        self._on_imp_select()

    def _view_refresh_backups(self):
        self.bk_box.delete(0, 'end')
        files = self.backups.list_files()
        self.checked_backups = {n for n in self.checked_backups if any(f['name'] == n for f in files)}
        for f in files:
            self.bk_box.insert('end', f['name'])
        for i, f in enumerate(files):
            if f['name'] in self.checked_backups:
                self.bk_box.selection_set(i)

    # ---------------- 订阅 ----------------
    def _on_cand_menu(self, event):
        row = self.cand_tree.identify_row(event.y)
        if row:
            self.show_candidate_menu(event, int(row))

    def _on_imp_menu(self, event):
        row = self.imp_tree.identify_row(event.y)
        if row:
            self.show_imported_menu(event, int(row))

    def _on_sub_menu(self, event):
        row = self.sub_tree.identify_row(event.y)
        if row:
            self.show_sub_menu(event, int(row))

    def _on_sub_click(self, event):
        row = self.sub_tree.identify_row(event.y)
        if row and 0 <= int(row) < len(self.subscriptions):
            self.do_show_subscription_sources(self.subscriptions[int(row)])

    def _on_sub_double(self, event):
        row = self.sub_tree.identify_row(event.y)
        if row and 0 <= int(row) < len(self.subscriptions):
            self.do_update_subscription(self.subscriptions[int(row)])

    def _view_refresh_subscriptions(self):
        tree = self.sub_tree
        tree.delete(*tree.get_children())
        tree.tag_configure('cur', background=self.C['card2'], foreground=self.C['text'])
        for i, sub in enumerate(self.subscriptions):
            tag = sub.get('last_tag')
            tree.insert('', 'end', iid=str(i),
                        values=(short(sub.get('repo', ''), 28), self._sub_meta_text(sub)),
                        tags=('cur',) if sub.get('repo') == self._current_sub else ())

    def _view_apply_backup_visible(self):
        try:
            if self.settings.get('backup_enabled', True):
                self._bk_card.grid()
            else:
                self._bk_card.grid_remove()
        except Exception:
            pass

    def _view_apply_log_visible(self):
        try:
            show = self.settings.get('log_enabled', True) and self.settings.get('log_window', True)
            if show:
                self._lg_card.grid()
            else:
                self._lg_card.grid_remove()
        except Exception:
            pass

    def _view_refresh_settings_row(self):
        try:
            self.dl_var.set(self.DL_LABELS.get(self.settings.get('downloader', 'auto'), '自动'))
        except Exception:
            pass
        try:
            if hasattr(self, 'cfg_dl_var'):
                self.cfg_dl_var.set(self.DL_LABELS.get(self.settings.get('downloader', 'auto'), '自动'))
            if hasattr(self, 'cfg_dl_status'):
                self.cfg_dl_status.configure(text=self._downloader_status_text())
        except Exception:
            pass

    def do_open_settings(self):
        C = self.C
        if self._settings_win is not None:
            try:
                if self._settings_win.winfo_exists():
                    self._settings_win.lift()
                    return
            except Exception:
                pass
        win = tk.Toplevel(self.root)
        self._settings_win = win
        win.title('设置')
        win.configure(bg=C['bg'])
        win.resizable(False, False)
        win.transient(self.root)
        win.protocol('WM_DELETE_WINDOW', self._on_settings_close)
        win.grid_columnconfigure(0, weight=1)

        def sec(title, row):
            f = tk.Frame(win, bg=C['card'], highlightthickness=1, highlightbackground=C['border'])
            f.grid(row=row, column=0, sticky='ew', padx=16, pady=(10, 0))
            f.grid_columnconfigure(1, weight=1)
            tk.Label(f, text=title, bg=C['card'], fg=C['text'], font=(FONT_FAMILY, 12, 'bold')).grid(
                row=0, column=0, columnspan=3, sticky='w', padx=14, pady=(10, 4))
            return f

        def wlab(f, r, text, col=0):
            tk.Label(f, text=text, bg=C['card'], fg=C['text'], font=(FONT_FAMILY, 10), anchor='w').grid(
                row=r, column=col, sticky='w', padx=(14, 8), pady=4)

        def wsub(f, r, text):
            tk.Label(f, text=text, bg=C['card'], fg=C['faint'], font=(FONT_FAMILY, 9), anchor='w').grid(
                row=r, column=1, columnspan=2, sticky='w', padx=14, pady=(0, 4))

        def wentry(f, r, value, on_change, width=34):
            e = tk.Entry(f, bg=C['field'], fg=C['text'], insertbackground=C['text'], relief='flat',
                         highlightthickness=1, highlightbackground=C['border'],
                         font=(FONT_FAMILY, 10), width=width)
            e.grid(row=r, column=1, sticky='ew', padx=(0, 8), pady=4)
            e.insert(0, value)
            e.bind('<Return>', lambda ev: on_change(e.get()))
            e.bind('<FocusOut>', lambda ev: on_change(e.get()))
            return e

        def wcheck(f, r, var, label, on_toggle):
            WebCheck(f, variable=var, command=on_toggle).grid(row=r, column=0, padx=(14, 4), pady=4)
            wlab(f, r, label, 1)

        f1 = sec('一、备份配置', 0)
        self.cfg_backup_var = tk.BooleanVar(value=self.settings.get('backup_enabled', True))
        wcheck(f1, 1, self.cfg_backup_var, '自动备份（每次写操作前备份；关闭后隐藏备份模块）',
               lambda: self.do_set_backup_enabled(self.cfg_backup_var.get()))
        wlab(f1, 2, '备份文件夹', 0)
        self.cfg_backup_entry = wentry(f1, 2, effective_backup_dir(self.settings), self.do_set_backup_dir)
        ttk.Button(f1, text='浏览…', command=lambda: self._pick_dir_to(self.cfg_backup_entry, self.do_set_backup_dir)).grid(
            row=2, column=2, padx=(0, 14), pady=4)
        wsub(f1, 3, '更改目录时可将旧备份迁移到新位置')

        f2 = sec('二、订阅配置', 1)
        wlab(f2, 1, '下载目录', 0)
        self.cfg_dl_entry = wentry(f2, 1, effective_download_dir(self.settings), self.do_set_download_dir)
        ttk.Button(f2, text='浏览…', command=lambda: self._pick_dir_to(self.cfg_dl_entry, self.do_set_download_dir)).grid(
            row=1, column=2, padx=(0, 14), pady=4)
        wsub(f2, 2, '每个订阅存放于 下载目录/<仓库名>/ 子文件夹；zip 自动解压，旧版本归档到 history/')
        wlab(f2, 3, '下载方式', 0)
        self.cfg_dl_var = tk.StringVar(value=self.DL_LABELS.get(self.settings.get('downloader', 'auto'), '自动'))
        self.cfg_dl_box = ttk.Combobox(f2, textvariable=self.cfg_dl_var, values=list(self.DL_LABELS.values()),
                                       state='readonly', width=8)
        self.cfg_dl_box.grid(row=3, column=1, sticky='w', padx=(0, 8), pady=4)
        self.cfg_dl_box.bind('<<ComboboxSelected>>', lambda e: self._on_downloader_pick(self.cfg_dl_var.get()))
        self.cfg_dl_status = tk.Label(f2, text=self._downloader_status_text(), bg=C['card'], fg=C['faint'],
                                      font=(FONT_FAMILY, 9), anchor='w')
        self.cfg_dl_status.grid(row=3, column=2, sticky='w', padx=(0, 10), pady=4)
        ttk.Button(f2, text='测试 ABDM', command=self.do_test_abdm).grid(row=3, column=3, padx=(0, 8), pady=4)
        ttk.Button(f2, text='指定 ABDM…', command=self.do_pick_abdm).grid(row=3, column=4, padx=(0, 14), pady=4)
        self.cfg_hist_var = tk.BooleanVar(value=self.settings.get('keep_history', True))
        wcheck(f2, 4, self.cfg_hist_var, '保留历史版本（关闭后更新时直接清除旧版本）',
               lambda: self.do_set_keep_history(self.cfg_hist_var.get()))
        wlab(f2, 5, '已有订阅', 0)
        self.cfg_sublist = tk.Listbox(f2, height=3, bg=C['field'], fg=C['text'], relief='flat',
                                      highlightthickness=1, highlightbackground=C['border'],
                                      font=(FONT_FAMILY, 10), selectbackground=C['card2'],
                                      selectforeground=C['text'])
        self.cfg_sublist.grid(row=5, column=1, columnspan=2, sticky='ew', padx=(0, 14), pady=4)
        for s in self.subscriptions:
            self.cfg_sublist.insert('end', s.get('repo', ''))
        ttk.Button(f2, text='打开文件夹', command=self._open_cfg_sub_dir).grid(row=6, column=1, sticky='w', padx=(0, 8), pady=(0, 10))
        ttk.Button(f2, text='删除订阅', command=self._delete_cfg_sub).grid(row=6, column=2, sticky='w', padx=(0, 14), pady=(0, 10))

        f3 = sec('三、日志配置', 2)
        self.cfg_log_var = tk.BooleanVar(value=self.settings.get('log_enabled', True))
        self.cfg_log_check = WebCheck(f3, variable=self.cfg_log_var,
                                      command=lambda: self.do_set_log_enabled(self.cfg_log_var.get()))
        self.cfg_log_check.grid(row=1, column=0, padx=(14, 4), pady=4)
        wlab(f3, 1, '记录日志（写入 config/logs/app.log）', 1)
        self.cfg_logwin_var = tk.BooleanVar(
            value=self.settings.get('log_enabled', True) and self.settings.get('log_window', True))
        self.cfg_logwin_check = WebCheck(f3, variable=self.cfg_logwin_var,
                                         command=lambda: self.do_set_log_window(self.cfg_logwin_var.get()))
        self.cfg_logwin_check.grid(row=2, column=0, padx=(14, 4), pady=4)
        self.cfg_logwin_label = tk.Label(f3, text='显示日志窗口（需先开启记录日志）', bg=C['card'],
                                         fg=C['text'], font=(FONT_FAMILY, 10), anchor='w')
        self.cfg_logwin_label.grid(row=2, column=1, columnspan=2, sticky='w', padx=(14, 8), pady=4)
        self._view_refresh_cfg_logwin()

        btns = ttk.Frame(win)
        btns.grid(row=3, column=0, sticky='e', padx=16, pady=12)
        ttk.Button(btns, text='关闭', command=self._on_settings_close).pack(side='left')
        try:
            win.update_idletasks()
            w = max(620, win.winfo_reqwidth() + 30)
            h = win.winfo_reqheight() + 12
            x = self.root.winfo_rootx() + max((self.root.winfo_width() - w) // 2, 0)
            y = self.root.winfo_rooty() + max((self.root.winfo_height() - h) // 2, 0)
            win.geometry('{}x{}+{}+{}'.format(w, h, x, y))
        except Exception:
            pass

    def _view_rebalance_bottom(self):
        # 隐藏某个底部模块时重排网格，让剩余卡片自动瓜分全部宽度
        try:
            show_bk = self.settings.get('backup_enabled', True)
            show_lg = self.settings.get('log_enabled', True) and self.settings.get('log_window', True)
            cards = []
            weights = []
            if show_bk:
                cards.append(self._bk_card)
                weights.append(2)
            cards.append(self._sub_card)
            weights.append(3)
            if show_lg:
                cards.append(self._lg_card)
                weights.append(3)
            for i, card in enumerate(cards):
                left = 0 if i == 0 else 5
                right = 0 if i == len(cards) - 1 else 5
                card.grid(row=0, column=i, sticky='nsew', padx=(left, right))
            for i in range(3):
                w = weights[i] if i < len(weights) else 0
                # 权重为 0 的列退出 uniform 组，否则 Tk 会按 weight=1 分走宽度
                self._bottom.grid_columnconfigure(i, weight=w, uniform=('bot' if w > 0 else ''))
        except Exception:
            pass

    def _view_refresh_cfg_logwin(self):
        # 记录日志关闭时：显示日志窗口自动关闭并置灰；开启时恢复可点
        C = self.C
        try:
            enabled = self.settings.get('log_enabled', True)
            if hasattr(self, 'cfg_logwin_var'):
                self.cfg_logwin_var.set(enabled and self.settings.get('log_window', True))
            if hasattr(self, 'cfg_logwin_check'):
                self.cfg_logwin_check.set_state(enabled)
            if hasattr(self, 'cfg_logwin_label'):
                self.cfg_logwin_label.configure(fg=C['text'] if enabled else C['faint'])
        except Exception:
            pass

    def _view_input(self, title, prompt, password=False):
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.configure(bg=self.C['card'])
        dlg.transient(self.root)
        tk.Label(dlg, text=prompt, bg=self.C['card'], fg=self.C['text'], wraplength=400, justify='left',
                 font=(FONT_FAMILY, 10)).pack(padx=20, pady=(16, 10), anchor='w')
        var = tk.StringVar()
        e = ttk.Entry(dlg, textvariable=var, show='*' if password else '')
        e.pack(padx=20, pady=(0, 12), fill='x')
        result = {'val': None}

        def ok():
            result['val'] = var.get().strip()
            dlg.destroy()

        e.bind('<Return>', lambda ev: ok())
        btns = ttk.Frame(dlg)
        btns.pack(pady=(0, 14))
        ttk.Button(btns, text='取消', command=dlg.destroy).pack(side='left', padx=8)
        ttk.Button(btns, text='确定', style='Accent.TButton', command=ok).pack(side='left', padx=8)
        try:
            dlg.update_idletasks()
            w = max(460, dlg.winfo_reqwidth() + 40)
            h = dlg.winfo_reqheight() + 16
            x = self.root.winfo_rootx() + max((self.root.winfo_width() - w) // 2, 0)
            y = self.root.winfo_rooty() + max((self.root.winfo_height() - h) // 2, 0)
            dlg.geometry('{}x{}+{}+{}'.format(w, h, x, y))
        except Exception:
            pass
        dlg.grab_set()
        dlg.wait_window()
        return result['val']

    def _view_log(self, text, level='info'):
        try:
            self.logbox.configure(state='normal')
            self.logbox.insert('end', text + '\n', level)
            self.logbox.see('end')
            self.logbox.configure(state='disabled')
        except Exception:
            pass

    def _view_set_status(self, text):
        self.status_var.set(text)

    def _view_confirm(self, title, message, danger=False):
        return bool(messagebox.askyesno(title, message, parent=self.root))

    def _view_info(self, title, message):
        messagebox.showinfo(title, message, parent=self.root)

    def _view_show_detail(self, title, text):
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.geometry('680x480')
        dlg.configure(bg=self.C['card'])
        dlg.transient(self.root)
        tb = tk.Text(dlg, bg=self.C['field'], fg=self.C['text'], font=(FONT_FAMILY, 10), wrap='word')
        tb.pack(fill='both', expand=True, padx=12, pady=(12, 4))
        tb.insert('1.0', text)
        tb.configure(state='disabled')
        ttk.Button(dlg, text='关闭', command=dlg.destroy).pack(pady=(0, 12))

    def _view_ask_folder(self):
        return filedialog.askdirectory(title='选择包含音源脚本的文件夹（将遍历所有子文件夹）',
                                       parent=self.root, initialdir=self.last_folder)

    def _view_ask_file(self):
        init = os.path.dirname(self.user_api_path) if self.user_api_path else None
        if init and not os.path.isdir(init):
            init = None
        return filedialog.askopenfilename(title='选择 user_api.json', parent=self.root,
                                          filetypes=[('JSON 文件', '*.json'), ('所有文件', '*.*')], initialdir=init)


# ---------------------------------------------------------------- 图标 / 工具
def _make_icon(zoom=2):
    """用 PhotoImage 生成一个 24x24 蓝色圆角方块 + 白色播放三角形的图标。"""
    size = 24
    img = tk.PhotoImage(width=size, height=size)
    img.put(PALETTE['accent'], to=(2, 2, 21, 21))
    img.put(PALETTE['bg'], to=(2, 2, 3, 3))
    img.put(PALETTE['bg'], to=(20, 2, 21, 3))
    img.put(PALETTE['bg'], to=(2, 20, 3, 21))
    img.put(PALETTE['bg'], to=(20, 20, 21, 21))
    for d in range(5):
        y0, y1 = 12 - d, 12 + d
        x1 = 8 + 2 * (4 - d)
        img.put('#fffaf5', to=(8, y0, x1, y1))
    try:
        if zoom and zoom != 1:
            img = img.zoom(zoom, zoom)
    except Exception:
        pass
    return img


def _enable_dpi_awareness():
    if sys.platform == 'win32':
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ---------------------------------------------------------------- 自检
def run_selftest(force_ttk=False):
    import tempfile
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    print('== LX Music 音源工具 自检 ==')
    tmp = tempfile.mkdtemp(prefix='lxtool_test_')
    globals()['subscriptions_path'] = lambda: os.path.join(tmp, 'subscriptions.json')
    globals()['settings_path'] = lambda: os.path.join(tmp, 'settings.json')
    src = os.path.join(tmp, 'sources')
    os.makedirs(os.path.join(src, 'sub'))
    api = os.path.join(tmp, 'user_api.json')
    bk = os.path.join(tmp, 'backups')
    report = []

    def write_source(name, text, sub=False):
        p = os.path.join(src if not sub else os.path.join(src, 'sub'), name)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
        return p

    write_source('a.js', '/*!\n * @name 测试音源A\n * @description 描述A\n * @version 1.2.0\n * @author 作者A\n */\n;(function(){ globalThis.lx = globalThis.lx || {}; })()')
    write_source('b.js', '/*!\n * @name 已存在源\n * @description 更新版\n * @version 2.0.0\n * @author 作者B\n */\n;(function(){})()', sub=True)
    write_source('c.js', '/*!\n * @name 表情源🌷\n * @version 3.1\n */\n;(function(){})()')

    try:
        # ---- 核心逻辑 ----
        base_entry = {'id': 'user_api_000_1', 'name': '已存在源', 'description': '旧描述', 'version': '1.0.0',
                      'author': '旧作者', 'homepage': '', 'allowShowUpdateAlert': True,
                      'script': compress_script('/*!\n * @name 已存在源\n * @version 1.0.0\n */\n;(function(){})()')}
        with open(api, 'w', encoding='utf-8') as f:
            json.dump({'userApis': [base_entry]}, f, ensure_ascii=False, indent='\t')
        entries, err, msg = load_user_api(api)
        assert err is None and len(entries) == 1, (err, msg)
        sources = scan_source_folder(src)
        assert len(sources) == 3, len(sources)
        by_name = {s.name: s for s in sources}
        rep = apply_imports(entries, [by_name['测试音源A']], 'add')
        assert len(rep['added']) == 1
        rep = apply_imports(entries, [by_name['测试音源A']], 'add')
        assert len(rep['skipped']) == 1
        rep = apply_imports(entries, [by_name['已存在源']], 'update')
        assert len(rep['updated']) == 1
        assert entries[0]['version'] == '2.0.0' and entries[0]['author'] == '作者B'
        rep = apply_imports(entries, [by_name['表情源🌷']], 'update')
        assert len(rep['added']) == 1
        assert len(entries) == 3
        save_user_api(api, entries)
        entries2, _, _ = load_user_api(api)
        assert len(entries2) == 3 and entries2[0]['name'] == '已存在源' and entries2[0]['version'] == '2.0.0'
        raw = decompress_script(entries2[0]['script'])
        assert '2.0.0' in raw
        bm = BackupManager(bk)
        p1 = bm.create(api, 'manual')
        p2 = bm.create(api, 'auto')
        assert os.path.isfile(p1) and os.path.isfile(p2) and p1 != p2
        assert len(bm.list_files()) == 2
        bm.delete([os.path.basename(p2)])
        assert len(bm.list_files()) == 1
        report.append('核心逻辑 OK（扫描/解析/导入/更新/去重/备份/读写）')

        # ---- 订阅逻辑（本地，无网络） ----
        assert parse_repo_ref('guoyue2010/lxmusic-') == ('guoyue2010', 'lxmusic-')
        assert parse_repo_ref('https://github.com/guoyue2010/lxmusic-/releases') == ('guoyue2010', 'lxmusic-')
        assert parse_repo_ref('https://github.com/guoyue2010/lxmusic-') == ('guoyue2010', 'lxmusic-')
        try:
            parse_repo_ref('随便写写')
            raise AssertionError('parse_repo_ref 应拒绝无效输入')
        except ValueError:
            pass
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('src/a.js', '/*!\\n * @name zip源\\n * @version 1.0\\n */\\n;(function(){})()')
            z.writestr('readme.txt', 'not a js')
        items = _extract_js_from_zip(buf.getvalue())
        assert len(items) == 1 and items[0][0] == 'src/a.js'
        save_subscriptions([{'repo': 'a/b', 'last_tag': 'v1'}])
        subs = load_subscriptions()
        assert len(subs) == 1 and subs[0]['repo'] == 'a/b' and subs[0]['last_tag'] == 'v1'
        # 镜像与设置
        set_mirror('ghfast.top')
        assert get_mirror() == 'https://ghfast.top'
        assert mirrored_url('https://github.com/a/b') == 'https://ghfast.top/https://github.com/a/b'
        set_mirror('')
        assert mirrored_url('https://github.com/a/b') == 'https://github.com/a/b'
        save_settings(dict(DEFAULT_SETTINGS, mirror='', use_idm=False))
        st = load_settings()
        assert st['mirror'] == '' and st['use_idm'] is False
        assert st['backup_enabled'] is True and st['log_enabled'] is True and st['log_window'] is True
        save_settings(dict(DEFAULT_SETTINGS, mirror='https://gh-proxy.com', use_idm=True, keep_history=True))
        st = load_settings()
        assert st['mirror'] == 'https://gh-proxy.com' and st['use_idm'] is True and st['keep_history'] is True
        idm_path = find_idm_path()
        print('IDM 探测结果:', idm_path)
        report.append('订阅逻辑 OK（仓库解析/zip 解包/状态存取/镜像设置）')

        # ---- UI 冒烟（隐藏窗口） ----
        if not force_ttk:
            if ensure_customtkinter():
                try:
                    app = CtkApp(user_api_path=api, backup_dir=bk, auto_confirm=True, hidden=True)
                    app.root.update_idletasks()
                    app.subscriptions = [{'repo': 'guoyue2010/lxmusic-', 'last_tag': 'V260810'}]
                    app._view_refresh_subscriptions()
                    app.root.update_idletasks()
                    assert len(app.sub_rows) == 1
                    # WebCheck 网页风格复选框
                    wc = WebCheck(app.root)
                    assert wc.var.get() is False
                    wc._on_click(None)
                    assert wc.var.get() is True
                    wc.destroy()
                    # 单击订阅 → 把本地已下载音源加载进待导入列表
                    subdir = os.path.join(tmp, 'dl', 'a', 'b')
                    os.makedirs(subdir)
                    with open(os.path.join(subdir, 'x.js'), 'w', encoding='utf-8') as f:
                        f.write('/*!\n * @name 订阅源\n * @version 1.0\n */\n;(function(){})()')
                    app.settings['download_dir'] = os.path.join(tmp, 'dl')
                    app.subscriptions = [{'repo': 'a/b', 'last_tag': 'v1'}]
                    app.do_show_subscription_sources(app.subscriptions[0])
                    app.root.update_idletasks()
                    assert len(app.candidates) == 1 and app.candidates[0].name == '订阅源'
                    app.candidates = []
                    # 解压后自动删除原压缩包
                    zbuf = io.BytesIO()
                    with zipfile.ZipFile(zbuf, 'w') as z:
                        z.writestr('pkg/a.js', '/*!\n * @name 解压源\n * @version 1.0\n */\n;(function(){})()')
                    zdir = os.path.join(tmp, 'ztest')
                    os.makedirs(zdir, exist_ok=True)
                    zpath = os.path.join(zdir, 'bundle.zip')
                    with open(zpath, 'wb') as f:
                        f.write(zbuf.getvalue())
                    app.settings['download_dir'] = os.path.join(tmp, 'dz')
                    sub2 = {'repo': 'z/z', 'last_tag': 'v1'}
                    scripts2 = app._extract_asset_main(zpath, 'bundle.zip', 'test', app._sub_download_dir(sub2))
                    assert len(scripts2) == 1 and scripts2[0].name == '解压源'
                    assert not os.path.exists(zpath), '解压后应删除原压缩包'
                    assert os.path.isfile(os.path.join(app._sub_download_dir(sub2), 'pkg', 'a.js'))
                    app.do_scan_folder(src)
                    app.root.update_idletasks()
                    assert len(app.candidates) == 3
                    app.do_import(all_selected=True)
                    app.root.update_idletasks()
                    n_after_import = len(app.entries)
                    app.do_clear_imported()
                    app.root.update_idletasks()
                    assert len(app.entries) == 0
                    app.checked_backups = {os.path.basename(p1)}
                    app.do_restore_backup()
                    app.root.update_idletasks()
                    assert len(app.entries) == 3, '还原后应为 3 个音源，实际 {}'.format(len(app.entries))
                    report.append('customtkinter 界面 OK（导入 {} → 清除 → 还原 {} 个音源）'.format(n_after_import, len(app.entries)))
                    app.root.destroy()
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    report.append('customtkinter 界面失败：{!r}'.format(e))
            else:
                report.append('customtkinter 不可用，跳过')
        try:
            app2 = TtkApp(user_api_path=api, backup_dir=bk, auto_confirm=True, hidden=True)
            app2.root.update_idletasks()
            app2.subscriptions = [{'repo': 'guoyue2010/lxmusic-', 'last_tag': 'V260810'}]
            app2._view_refresh_subscriptions()
            app2.root.update_idletasks()
            assert len(app2.sub_tree.get_children()) == 1
            app2.do_scan_folder(src)
            app2.root.update_idletasks()
            app2.do_import(all_selected=True)
            app2.root.update_idletasks()
            report.append('ttk 回退界面 OK（导入后共 {} 个音源）'.format(len(app2.entries)))
            app2.root.destroy()
        except Exception as e:
            import traceback
            traceback.print_exc()
            report.append('ttk 回退界面失败：{!r}'.format(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('\n'.join(report))
    print('== 自检结束 ==')


# ---------------------------------------------------------------- 入口
def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    args = sys.argv[1:]
    if '--selftest' in args:
        run_selftest(force_ttk='--force-ttk' in args)
        return
    _enable_dpi_awareness()
    print('{}  v{}'.format(APP_TITLE, __version__))
    print('数据文件：{}'.format(default_user_api_path() or '(未找到 APPDATA)'))
    if '--force-ttk' in args or not ensure_customtkinter():
        TtkApp().run()
    else:
        CtkApp().run()


if __name__ == '__main__':
    main()
