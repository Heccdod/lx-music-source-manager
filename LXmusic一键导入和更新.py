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


def short(text, n):
    """文本截断（None 安全）。"""
    text = '' if text is None else str(text)
    return text if len(text) <= n else text[:n - 1] + '…'


def normalize_name(name):
    return (name or '').strip().casefold()


def hex_rgb(h):
    """'#rrggbb' -> (r, g, b)。"""
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def read_text_auto(path):
    """按多种编码尝试读取文本文件，返回 (文本, 编码)。"""
    with open(path, 'rb') as f:
        data = f.read()
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
    base = os.path.dirname(os.path.abspath(sys.argv[0]))
    cands = [
        os.path.join(base, 'lx_backups'),
        os.path.join(os.environ.get('LOCALAPPDATA', base), 'LXMusicTool', 'backups'),
    ]
    for cand in cands:
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, '.probe')
            with open(probe, 'w') as f:
                f.write('ok')
            os.remove(probe)
            return cand
        except Exception:
            continue
    return os.path.join(base, 'lx_backups')


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
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules',)]
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
    def __init__(self, user_api_path=None, backup_dir=None, auto_confirm=False):
        self.auto_confirm = auto_confirm
        self.user_api_path = user_api_path if user_api_path is not None else default_user_api_path()
        self.backup_dir = backup_dir if backup_dir is not None else default_backup_dir()
        self.backups = BackupManager(self.backup_dir)
        self.entries = []
        self.candidates = []
        self.checked_candidates = set()
        self.checked_imported = set()
        self.checked_backups = set()
        self.candidate_filter = ''
        self.import_mode = 'add'
        self.last_folder = os.path.expanduser('~')
        self._load_data()
        self._view_refresh_backups()

    # ---------------- 日志 / 提示 ----------------
    def log(self, text, level='info'):
        self._view_log('[{}] {}'.format(time.strftime('%H:%M:%S'), text), level)

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
            self.path_label.configure(text=short('数据文件：' + (self.user_api_path or '未定位'), 88))
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
        self._view_set_status('数据文件：{}  [{}]    备份目录：{}    修改后需重启 LX Music 生效'.format(p or '(未定位)', w, self.backup_dir))

    def _auto_backup(self):
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
        self.animations = not hidden
        self.SmoothFrame = smooth_scrollable_class()
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
        if self.animations:
            try:
                self.root.attributes('-alpha', 0.0)
            except Exception:
                pass
            self._fade_in(self.root)

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
        self.f_title = ctk.CTkFont(family=FONT_FAMILY, size=18, weight='bold')
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
        ctk.CTkEntry(card, textvariable=self.search_var, placeholder_text='搜索音源名称 / 版本 / 作者 / 路径…',
                     height=30, corner_radius=6, fg_color=C['field'], border_color=C['border'], border_width=1,
                     text_color=C['text'], placeholder_text_color=C['faint'], font=self.f_small).grid(
            row=2, column=0, sticky='ew', padx=14, pady=(2, 4))

        self.cand_list = self.SmoothFrame(card, fg_color=C['card'], corner_radius=0,
                                          scrollbar_button_color=C['border'], scrollbar_button_hover_color=C['faint'])
        self.cand_list.grid(row=3, column=0, sticky='nsew', padx=10, pady=2)
        self.cand_rows = {}

        seg_row = ctk.CTkFrame(card, fg_color='transparent')
        seg_row.grid(row=4, column=0, sticky='ew', padx=14, pady=(8, 0))
        ctk.CTkLabel(seg_row, text='导入模式', font=self.f_small, text_color=C['muted']).pack(side='left', padx=(0, 8))
        self.mode_var = tk.StringVar(value=MODE_ADD_LABEL)
        self.mode_seg = ctk.CTkSegmentedButton(
            seg_row, values=[MODE_ADD_LABEL, MODE_UPDATE_LABEL], variable=self.mode_var,
            command=lambda v: self._set_mode(v), height=30, corner_radius=6,
            selected_color=C['accent'], selected_hover_color=C['accent_hover'],
            unselected_color=C['field'], unselected_hover_color=C['hover'],
            text_color=C['text'], font=self.f_small)
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

        cols = ctk.CTkFrame(card, fg_color='transparent')
        cols.grid(row=1, column=0, sticky='ew', padx=18, pady=(4, 2))
        cols.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(cols, text='名称', font=self.f_tiny, text_color=C['faint']).grid(row=0, column=0, sticky='w', padx=(14, 8))
        ctk.CTkLabel(cols, text='版本', font=self.f_tiny, text_color=C['faint']).grid(row=0, column=1, sticky='w', padx=(0, 8))
        ctk.CTkLabel(cols, text='作者', font=self.f_tiny, text_color=C['faint']).grid(row=0, column=2, sticky='w', padx=(0, 8))
        ctk.CTkLabel(cols, text='描述', font=self.f_tiny, text_color=C['faint']).grid(row=0, column=3, sticky='w')

        self.imp_list = self.SmoothFrame(card, fg_color=C['card'], corner_radius=0,
                                         scrollbar_button_color=C['border'], scrollbar_button_hover_color=C['faint'])
        self.imp_list.grid(row=2, column=0, sticky='nsew', padx=10, pady=2)
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
        self.bk_list = self.SmoothFrame(bk, fg_color=C['card'], corner_radius=0, height=112,
                                        scrollbar_button_color=C['border'], scrollbar_button_hover_color=C['faint'])
        self.bk_list.grid(row=1, column=0, sticky='ew', padx=10, pady=(2, 10))
        self.bk_rows = {}

        lg = ctk.CTkFrame(bottom, fg_color=C['card'], corner_radius=8)
        lg.grid(row=0, column=1, sticky='nsew', padx=(6, 0))
        lg.grid_columnconfigure(0, weight=1)
        lg.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(lg, fg_color='transparent')
        head.grid(row=0, column=0, sticky='ew', padx=14, pady=(12, 2))
        head.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(head, text='运行日志', font=self.f_card, text_color=C['text']).grid(row=0, column=0, sticky='w')
        self._btn(head, '清空日志', self.do_clear_log, width=80).grid(row=0, column=1, sticky='e')
        self.logbox = ctk.CTkTextbox(lg, fg_color=C['field'], corner_radius=6, font=self.f_log,
                                     wrap='word', height=112, state='disabled')
        self.logbox.grid(row=1, column=0, sticky='nsew', padx=10, pady=(2, 10))
        for tag, color in LOG_COLORS.items():
            self.logbox.tag_config(tag, foreground=color)

    def do_clear_log(self):
        self.logbox.configure(state='normal')
        self.logbox.delete('1.0', 'end')
        self.logbox.configure(state='disabled')

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

    def _fade_in(self, win, step=0, steps=9, interval=22):
        """窗口 / 对话框淡入。"""
        try:
            win.attributes('-alpha', min(1.0, (step + 1) / steps))
            if step + 1 < steps:
                win.after(interval, lambda: self._fade_in(win, step + 1, steps, interval))
        except Exception:
            pass

    # ---------------- 候选行 ----------------
    def _build_candidate_row(self, i):
        # 行使用原生 tk 组件（无画布绘制层），滚动不产生拖尾；无勾选框，纯底色表达选中态
        C = self.C
        s = self.candidates[i]
        row_bg = C['card2'] if i in self.checked_candidates else C['card']
        row = tk.Frame(self.cand_list, bg=row_bg, cursor='hand2')
        row.pack(fill='x', padx=4, pady=3)
        name = tk.Label(row, text=short(s.name, 22), bg=row_bg, fg=C['text'], font=self.f_bold,
                        anchor='w', cursor='hand2')
        name.grid(row=0, column=0, sticky='w', padx=(14, 6), pady=9)
        ver = tk.Label(row, text=short('v' + s.version, 14), bg=row_bg, fg=C['accent'], font=self.f_tiny,
                       anchor='w', cursor='hand2')
        ver.grid(row=0, column=1, sticky='w', padx=(0, 6), pady=9)
        aut = tk.Label(row, text=short(s.author or '—', 14), bg=row_bg, fg=C['muted'], font=self.f_small,
                       anchor='w', cursor='hand2')
        aut.grid(row=0, column=2, sticky='w', padx=(0, 6), pady=9)
        pat = tk.Label(row, text=s.rel_path, bg=row_bg, fg=C['faint'], font=self.f_tiny,
                       anchor='w', cursor='hand2')
        pat.grid(row=0, column=3, sticky='ew', padx=(0, 10), pady=9)
        row.grid_columnconfigure(3, weight=1)
        self.cand_rows[i] = row
        for w in (row, name, ver, aut, pat):
            w.bind('<Button-1>', lambda e, idx=i: self._cand_toggle(idx))
            w.bind('<Enter>', lambda e, idx=i, frm=row: self._row_enter(frm, idx))
            w.bind('<Leave>', lambda e, idx=i, frm=row: self._row_leave(frm, idx))
            w.bind('<Double-Button-1>', lambda e, idx=i: self._cand_detail(idx))

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
        row.pack(fill='x', padx=4, pady=3)
        name = tk.Label(row, text=short(e.get('name', ''), 20), bg=row_bg, fg=C['text'], font=self.f_bold,
                        anchor='w', cursor='hand2')
        name.grid(row=0, column=0, sticky='w', padx=(14, 8), pady=8)
        ver = tk.Label(row, text=short(str(e.get('version', '')), 12), bg=row_bg, fg=C['accent'], font=self.f_tiny,
                       anchor='w', cursor='hand2')
        ver.grid(row=0, column=1, sticky='w', padx=(0, 8), pady=8)
        aut = tk.Label(row, text=short(e.get('author') or '—', 12), bg=row_bg, fg=C['muted'], font=self.f_small,
                       anchor='w', cursor='hand2')
        aut.grid(row=0, column=2, sticky='w', padx=(0, 8), pady=8)
        des = tk.Label(row, text=short(e.get('description') or '', 34), bg=row_bg, fg=C['faint'], font=self.f_small,
                       anchor='w', cursor='hand2')
        des.grid(row=0, column=3, sticky='ew', padx=(0, 10), pady=8)
        row.grid_columnconfigure(3, weight=1)
        self.imp_rows[i] = row
        for w in (row, name, ver, aut, des):
            w.bind('<Button-1>', lambda ev, idx=i: self._imp_toggle(idx))
            w.bind('<Enter>', lambda ev, idx=i, frm=row: self._imp_enter(frm, idx))
            w.bind('<Leave>', lambda ev, idx=i, frm=row: self._imp_leave(frm, idx))
            w.bind('<Double-Button-1>', lambda ev, idx=i: self._imported_detail(idx))

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
        if self.animations:
            try:
                dlg.attributes('-alpha', 0.0)
            except Exception:
                pass
            self._fade_in(dlg, steps=6, interval=18)
            try:
                dlg.after(400, lambda: dlg.attributes('-alpha', 1.0))
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
        if self.animations:
            try:
                dlg.attributes('-alpha', 0.0)
            except Exception:
                pass
            self._fade_in(dlg, steps=6, interval=18)

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
        if self.animations:
            try:
                self.root.attributes('-alpha', 0.0)
            except Exception:
                pass
            self._fade_in_root()

    def _fade_in_root(self, step=0):
        try:
            self.root.attributes('-alpha', min(1.0, (step + 1) / 9))
            if step + 1 < 9:
                self.root.after(22, lambda: self._fade_in_root(step + 1))
        except Exception:
            pass

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
        ttk.Button(header, text='重新定位', command=self.do_relocate).grid(row=0, column=2, rowspan=2, sticky='e', padx=(0, 4))
        ttk.Button(header, text='打开数据目录', command=self.do_open_data_dir).grid(row=0, column=3, rowspan=2, sticky='e', padx=(4, 0))

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
        self.cand_tree = ttk.Treeview(left, columns=('chk', 'name', 'ver', 'author', 'path'), show='headings',
                                      selectmode='none')
        for col, txt, width, anchor in (('chk', '选', 36, 'center'), ('name', '音源名称', 180, 'w'),
                                        ('ver', '版本', 80, 'w'), ('author', '作者', 140, 'w'), ('path', '文件路径', 240, 'w')):
            self.cand_tree.heading(col, text=txt)
            self.cand_tree.column(col, width=width, anchor=anchor, stretch=(col == 'path'))
        self.cand_tree.tag_configure('checked', background=C['card2'], foreground=C['text'])
        self.cand_tree.grid(row=3, column=0, sticky='nsew', pady=2)
        self.cand_tree.bind('<Button-1>', self._on_cand_click)
        self.cand_tree.bind('<Double-1>', self._on_cand_double)
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
        self.imp_tree = ttk.Treeview(right, columns=('name', 'ver', 'author', 'desc'), show='headings',
                                     selectmode='extended')
        for col, txt, width in (('name', '名称', 160), ('ver', '版本', 90), ('author', '作者', 130), ('desc', '描述', 260)):
            self.imp_tree.heading(col, text=txt)
            self.imp_tree.column(col, width=width, anchor='w', stretch=(col == 'desc'))
        self.imp_tree.grid(row=1, column=0, sticky='nsew', pady=(4, 2))
        self.imp_tree.bind('<<TreeviewSelect>>', self._on_imp_select)
        self.imp_tree.bind('<Double-1>', self._on_imp_double)
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

        # ----- 底部：备份 + 日志 -----
        bottom = ttk.Frame(self.root)
        bottom.grid(row=2, column=0, sticky='ew', padx=12, pady=(4, 2))
        bottom.grid_columnconfigure(0, weight=2, uniform='bot')
        bottom.grid_columnconfigure(1, weight=3, uniform='bot')
        bk = ttk.Frame(bottom, style='Card.TFrame', padding=12)
        bk.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
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
        lg = ttk.Frame(bottom, style='Card.TFrame', padding=12)
        lg.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
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

    def do_clear_log(self):
        self.logbox.configure(state='normal')
        self.logbox.delete('1.0', 'end')
        self.logbox.configure(state='disabled')

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
                        values=(chk, short(s.name, 18), short('v' + s.version, 12),
                                short(s.author or '—', 12), s.rel_path),
                        tags=(('checked',) if i in self.checked_candidates else ()))
        self.cand_count.configure(text='共 {} 个 · 显示 {} · 已选 {}'.format(
            len(self.candidates), shown, len(self.checked_candidates)))
        self._update_action_buttons()

    def _view_refresh_imported(self):
        tree = self.imp_tree
        tree.delete(*tree.get_children())
        for i, e in enumerate(self.entries):
            tree.insert('', 'end', iid=str(i),
                        values=(short(e.get('name', ''), 18), short(str(e.get('version', '')), 12),
                                short(e.get('author') or '—', 12), short(e.get('description') or '', 30)))
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

        # ---- UI 冒烟（隐藏窗口） ----
        if not force_ttk:
            if ensure_customtkinter():
                try:
                    app = CtkApp(user_api_path=api, backup_dir=bk, auto_confirm=True, hidden=True)
                    app.root.update_idletasks()
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
