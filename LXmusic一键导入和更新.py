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

版权与非官方声明
----------------
本工具为非官方开源爱好者个人作品，仅供学习与技术交流使用，不内置、不提供、不分发任何音源脚本。
本项目与 lx-music-desktop（洛雪音乐）官方、Anthropic（Claude）、DeepSeek（深度求索）等任何组织或品牌均无关联；
界面中提及的配色方案名称仅用于描述视觉色彩风格，所涉开源字体（Noto Sans / Noto Serif / Inter / JetBrains Mono）均遵循 OFL-1.1 开源字体许可协议。
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
import urllib.parse
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

__version__ = '1.2.2'

APP_TITLE = 'LX Music 音源一键导入 / 更新工具'
FONT_FAMILY = 'Noto Sans SC'
FONT_SANS_BOLD = 'Noto Sans SC Medium'
FONT_SERIF = 'Noto Serif SC SemiBold'
FONT_MONO = 'JetBrains Mono'
MODE_ADD_LABEL = '仅新增'
MODE_UPDATE_LABEL = '同名更新'
_FONTS_INITIALIZED = False


def _ensure_claude_fonts(root=None):
    """加载 dsh-claude-style / Anthropic 风格字体（Inter / Noto Serif / JetBrains Mono / Noto SC），
    用 Windows GDI AddFontResourceExW 私有注册（无需管理员权限，进程内立即生效）。"""
    global FONT_FAMILY, FONT_SANS_BOLD, FONT_SERIF, FONT_MONO, _FONTS_INITIALIZED
    if _FONTS_INITIALIZED:
        return
    _FONTS_INITIALIZED = True
    if sys.platform == 'win32':
        try:
            import ctypes
            font_dir = os.path.join(config_dir(), 'fonts')
            os.makedirs(font_dir, exist_ok=True)
            dsh_fonts = os.path.expanduser(r'~\.dsh\profiles\desktop\node_modules\dsh-claude-style\lib\fonts')
            if os.path.isdir(dsh_fonts):
                for fn in ('JetBrainsMonoVariable.ttf',):
                    src = os.path.join(dsh_fonts, fn)
                    dst = os.path.join(font_dir, fn)
                    if os.path.isfile(src) and not os.path.isfile(dst):
                        try:
                            shutil.copy2(src, dst)
                        except Exception:
                            pass
                for woff_fn in ('InterVariable.woff2', 'NotoSerifVariable.woff2'):
                    src = os.path.join(dsh_fonts, woff_fn)
                    dst = os.path.join(font_dir, woff_fn.replace('.woff2', '.ttf'))
                    if os.path.isfile(src) and not os.path.isfile(dst):
                        try:
                            from fontTools.ttLib import TTFont
                            tf = TTFont(src)
                            tf.flavor = None
                            tf.save(dst)
                        except Exception:
                            pass
            for fn in os.listdir(font_dir):
                if fn.lower().endswith(('.ttf', '.otf')):
                    p = os.path.abspath(os.path.join(font_dir, fn))
                    try:
                        ctypes.windll.gdi32.AddFontResourceExW(p, 0x10, 0)
                    except Exception:
                        pass
        except Exception:
            pass
    try:
        import tkinter.font as tkfont
        fams = set(tkfont.families(root))
        for cand in ('Noto Sans SC', 'HarmonyOS Sans SC', 'Segoe UI Variable Text', 'Inter', 'Microsoft YaHei UI'):
            if cand in fams:
                FONT_FAMILY = cand
                break
        for cand in ('Noto Sans SC Medium', 'Segoe UI Variable Text Semibold', FONT_FAMILY):
            if cand in fams:
                FONT_SANS_BOLD = cand
                break
        for cand in ('Noto Serif SC SemiBold', 'Noto Serif SC', 'Source Han Serif SC', 'Noto Serif', 'Georgia', FONT_FAMILY):
            if cand in fams:
                FONT_SERIF = cand
                break
        for cand in ('JetBrains Mono', 'Consolas', FONT_FAMILY):
            if cand in fams:
                FONT_MONO = cand
                break
    except Exception:
        pass


# ---------------------------------------------------------------- 配色与主题
# 四套主题配色：清风（洛雪）/ 暖砂（类Claude）/ 鲸蓝（类Deepseek）/ 星月（暗夜）
THEMES = {
    'green': {
        'label': '清风（洛雪）',
        'bg': '#f1f6f3',
        'card': '#ffffff',
        'card_border': '#dce8e2',
        'card2': '#daf0e6',
        'row_sel': '#eef8f3',
        'field': '#f5f9f7',
        'border': '#cde0d6',
        'divider': '#eaf1ed',
        'hover': '#eaf3ee',
        'accent': '#1f8a65',
        'accent_hover': '#176e4f',
        'green': '#1f8a65',
        'green_bg': '#e3f3ec',
        'warn': '#a4621d',
        'warn_bg': '#faefe3',
        'danger': '#943333',
        'danger_bg': '#fbeae8',
        'text': '#12211b',
        'muted': '#556960',
        'faint': '#859890',
        'on_accent': '#ffffff',
    },
    'claude': {
        'label': '暖砂（类Claude）',
        'bg': '#f4f2f0',
        'card': '#ffffff',
        'card_border': '#e9e9e9',
        'card2': '#f6ded7',
        'row_sel': '#fdf3ef',
        'field': '#f7f6f5',
        'border': '#dedede',
        'divider': '#f0efed',
        'hover': '#f3f1ef',
        'accent': '#d97757',
        'accent_hover': '#c46343',
        'green': '#3d7550',
        'green_bg': '#e8f3ec',
        'warn': '#a4621d',
        'warn_bg': '#faefe3',
        'danger': '#943333',
        'danger_bg': '#fbeae8',
        'text': '#161616',
        'muted': '#70686a',
        'faint': '#91888a',
        'on_accent': '#ffffff',
    },
    'ocean': {
        'label': '鲸蓝（类Deepseek）',
        'bg': '#f4f6fb',
        'card': '#ffffff',
        'card_border': '#e4e7ef',
        'card2': '#e4eaff',
        'row_sel': '#f1f4ff',
        'field': '#f7f8fc',
        'border': '#d8dce8',
        'divider': '#eef0f6',
        'hover': '#eff2f9',
        'accent': '#4d6bfe',
        'accent_hover': '#3d56e9',
        'green': '#23865b',
        'green_bg': '#e5f4ed',
        'warn': '#b4690e',
        'warn_bg': '#fbf0e1',
        'danger': '#c93b3b',
        'danger_bg': '#fceaea',
        'text': '#131416',
        'muted': '#656871',
        'faint': '#848891',
        'on_accent': '#ffffff',
    },
    'dark': {
        'label': '星月（暗夜）',
        'bg': '#13151c',
        'card': '#1b1e28',
        'card_border': '#292e3d',
        'card2': '#242b44',
        'row_sel': '#20263b',
        'field': '#151820',
        'border': '#30364a',
        'divider': '#252938',
        'hover': '#242938',
        'accent': '#6e82f5',
        'accent_hover': '#5b70e8',
        'green': '#5ec294',
        'green_bg': '#1b2e26',
        'warn': '#deb068',
        'warn_bg': '#2e261a',
        'danger': '#e06c75',
        'danger_bg': '#321e22',
        'text': '#e8ecf4',
        'muted': '#9ca4b8',
        'faint': '#6d758a',
        'on_accent': '#ffffff',
    },
}
THEME_ORDER = ['green', 'claude', 'ocean', 'dark']

# 当前生效的配色（启动时由 apply_theme 原地填充，界面各处直接引用同一对象）
PALETTE = dict(THEMES['green'])
LOG_COLORS = {}


def apply_theme(name):
    """切换主题：原地更新 PALETTE，保证所有持有引用的地方立即同步。"""
    name = name if name in THEMES else 'green'
    PALETTE.clear()
    PALETTE.update(THEMES[name])
    PALETTE['_theme_key'] = name
    LOG_COLORS.clear()
    LOG_COLORS.update({
        'title': PALETTE['text'],
        'info': PALETTE['muted'],
        'ok': PALETTE['green'],
        'update': PALETTE['accent'],
        'warn': PALETTE['warn'],
        'error': PALETTE['danger'],
    })
    return name


apply_theme('green')

# 界面字号（基准值：针对 1080p/2.5K/4K 桌面环境加大基础像素字号，避免运行时重排字体树导致缩放/全屏卡顿）
FONT_BASE = dict(title=20, card=16, base=14, bold=14, small=13, tiny=12, btn=13, log=12)
UI_SCALE_MIN, UI_SCALE_MAX = 0.85, 2.0


def _viewport_font_boost(_width):
    """保持恒定 1.0，避免最大化/缩放跨越阈值时批量修改 CTkFont 触发整棵控件树同步重绘卡顿。"""
    return 1.0


def _dpi_scale():
    """固定返回 1.0：配合 CTk deactivate_automatic_dpi_awareness 与 Tk 原生字体渲染，
    避免把窗口几何尺寸乘上 1.5 导致 150% DPI 屏幕下窗口超出屏幕边界。"""
    return 1.0


def _ui_scale(v, default=1.0):
    """把配置里的界面缩放收敛到允许区间。"""
    try:
        v = float(v)
    except Exception:
        v = default
    return max(UI_SCALE_MIN, min(UI_SCALE_MAX, v))


def _screen_size():
    """取主屏逻辑分辨率（用完即销毁临时窗口，不残留隐藏的 Tk 根窗口）。"""
    try:
        r = tk.Tk()
        r.withdraw()
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.destroy()
        return sw, sh
    except Exception:
        return 1707, 1067


def _initial_size(scale):
    """计算初始窗口大小，严格限制在主屏可用区域内（150% DPI 下绝不超屏）。"""
    sw, sh = _screen_size()
    target_w = int(min(1340 * max(1.0, (scale - 1.0) * 0.5 + 1.0), sw * 0.86))
    target_h = int(min(850 * max(1.0, (scale - 1.0) * 0.5 + 1.0), sh * 0.86))
    return max(1060, target_w), max(680, target_h)


def _min_size(scale):
    """最小窗口尺寸：保证小屏和分屏下都能完整显示底部状态栏与操作区。"""
    sw, sh = _screen_size()
    return min(1060, int(sw * 0.72)), min(680, int(sh * 0.72))


def _scale_fonts(scale, spec):
    """按缩放把字号规格换算成实际字号。"""
    return {k: max(9, int(round(v * scale))) for k, v in spec.items()}


_CHK_IMG_CACHE = {}


def _get_checkbox_images(size=16, colors=None):
    """用 PIL 4x 超采样预渲染圆角抗锯齿复选框（off / on / hover / disabled），
    供列表行与 WebCheck 直接贴图，消除成百上千个 Canvas 重绘带来的卡顿。"""
    C = colors or PALETTE
    key = (size, C.get('accent'), C.get('field'), C.get('border'), C.get('hover'), C.get('card'))
    if key in _CHK_IMG_CACHE:
        return _CHK_IMG_CACHE[key]
    try:
        from PIL import Image, ImageDraw, ImageTk
        ss = 4
        S = size * ss
        pad = 2 * ss
        rad = 4 * ss

        def make_one(checked, hover=False, enabled=True):
            img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            if checked:
                fill = hex_rgb(C['accent'] if enabled else C['faint']) + (255,)
                d.rounded_rectangle((pad, pad, S - pad - 1, S - pad - 1), radius=rad, fill=fill)
                pts = [
                    (int(S * 0.27), int(S * 0.52)),
                    (int(S * 0.44), int(S * 0.69)),
                    (int(S * 0.74), int(S * 0.31)),
                ]
                fg = hex_rgb(C.get('on_accent', '#ffffff')) + (255,)
                d.line(pts, fill=fg, width=int(2.1 * ss), joint='curve')
            else:
                bg_hex = C['hover'] if (hover and enabled) else C['field']
                bd_hex = C['accent'] if (hover and enabled) else (C['border'] if enabled else C['divider'])
                d.rounded_rectangle(
                    (pad, pad, S - pad - 1, S - pad - 1),
                    radius=rad,
                    fill=hex_rgb(bg_hex) + (255,),
                    outline=hex_rgb(bd_hex) + (255,),
                    width=int(1.4 * ss),
                )
            small = img.resize((size, size), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(small)

        res = {
            'off': make_one(False, False, True),
            'hover': make_one(False, True, True),
            'on': make_one(True, False, True),
            'dis_off': make_one(False, False, False),
            'dis_on': make_one(True, False, False),
        }
        _CHK_IMG_CACHE[key] = res
        return res
    except Exception:
        return None


class WebCheck(tk.Canvas):
    """dsh-claude-style 圆角抗锯齿复选框：优先使用预渲染超采样贴图，极速流畅。"""

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
        if self._hover == h:
            return
        self._hover = h
        self._draw()

    def _draw(self):
        c = self
        c.delete('all')
        s = self._size
        imgs = _get_checkbox_images(s, self._colors)
        if imgs is not None:
            if not self._enabled:
                k = 'dis_on' if self.var.get() else 'dis_off'
            elif self.var.get():
                k = 'on'
            else:
                k = 'hover' if self._hover else 'off'
            self._cur_img = imgs[k]
            c.create_image(s // 2, s // 2, image=self._cur_img)
            return
        pad = 2
        if self.var.get():
            fill = self._colors['accent'] if self._enabled else self._colors['faint']
            c.create_rectangle(pad, pad, s - pad, s - pad, fill=fill, outline=fill, width=1)
            c.create_line(int(s * 0.26), int(s * 0.52),
                          int(s * 0.45), int(s * 0.72),
                          int(s * 0.76), int(s * 0.30),
                          fill=PALETTE.get('on_accent', '#ffffff'), width=2,
                          capstyle=tk.ROUND, joinstyle=tk.ROUND)
        else:
            if self._enabled:
                outline = self._colors['accent'] if self._hover else self._colors['muted']
                fill = self._colors['hover'] if self._hover else self._colors['field']
            else:
                outline = self._colors['border']
                fill = self._colors['field']
            c.create_rectangle(pad, pad, s - pad, s - pad, fill=fill, outline=outline, width=1.5)


def short(text, n):
    """文本截断（None 安全）。"""
    text = '' if text is None else str(text)
    return text if len(text) <= n else text[:n - 1] + '…'


def version_key(version):
    """版本号比较键：先比数字序列，再比原字符串（用于同批同名音源取最高版本）。"""
    text = str(version or '')
    return ([int(x) for x in re.findall(r'\d+', text)], text)


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


def _raw_crc(text):
    """脚本原文的校验值，用于判断「同版本但内容变了」。"""
    return zlib.crc32((text or '').encode('utf-8', 'replace')) & 0xFFFFFFFF


def _same_content(compressed, raw):
    """比较已存压缩脚本与磁盘原文是否同一份（解压后比 CRC）。"""
    try:
        return _raw_crc(decompress_script(compressed or '')) == _raw_crc(raw)
    except Exception:
        return False


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
_LINE_META_RE = re.compile(r'^\s*//\s?@(\w+)\s+(.+)$')


def _head_lines(text, limit=60):
    """取脚本开头的若干行——元数据只可能在文件头部。"""
    return text[:8192].splitlines()[:limit]


def _block_comment(text):
    r"""返回脚本头部的 /* ... */ 注释块（找不到返回空串）。"""
    head = chr(10).join(_head_lines(text))
    m = _BLOCK_RE.search(head)
    return m.group(0) if m else ''


def parse_script_meta(text, fallback_name=''):
    """解析脚本头部注释块中的元数据，规则与官方 parseScriptInfo 一致。

    额外兼容只用 `// @name ...` 行注释的音源脚本：这类脚本原先被判定为
    「没有元数据」，名称退化成文件名、版本退化成 1.0.0，会让「智能勾选」
    把已装的同版音源误判成可升级。
    """
    info = {k: '' for k in INFO_LIMITS}
    block = _block_comment(text)
    lines = block.splitlines() if block else []
    for line in lines + _head_lines(text):
        r = _META_RE.match(line)
        if not r:
            r = _LINE_META_RE.match(line)
        if r and r.group(1) in INFO_LIMITS and not info[r.group(1)]:
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
        meta_missing = not _block_comment(text) and not any(
            _LINE_META_RE.match(l) for l in _head_lines(text))
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


def _open_url(url, timeout=30):
    req = urllib.request.Request(mirrored_url(url), headers=_GITHUB_HEADERS)
    return urllib.request.urlopen(req, timeout=timeout)


def download_bytes(url, timeout=30):
    """下载 Release 附件（自动跟随跳转；设置了镜像时走镜像前缀）。"""
    with _open_url(url, timeout) as resp:
        return resp.read()


def download_to_file(url, target, on_progress=None, timeout=30, chunk=65536):
    """流式下载到 target：边下边写盘并回报进度，返回写入字节数。
    on_progress(done, total)：total 为 0 表示服务器没给 Content-Length。
    先写 .part 再改名，避免半截文件被当成完整音源。"""
    tmp = target + '.part'
    done = 0
    try:
        with _open_url(url, timeout) as resp:
            try:
                total = int(resp.headers.get('Content-Length') or 0)
            except Exception:
                total = 0
            with open(tmp, 'wb') as fh:
                while True:
                    buf = resp.read(chunk)
                    if not buf:
                        break
                    fh.write(buf)
                    done += len(buf)
                    if on_progress:
                        try:
                            on_progress(done, total)
                        except Exception:
                            pass
        os.replace(tmp, target)
        return done
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise


def human_size(n):
    """字节数转人读字符串（B / KB / MB）。"""
    try:
        n = float(n or 0)
    except Exception:
        return '?'
    if n < 1024:
        return '{:.0f} B'.format(n)
    if n < 1024 * 1024:
        return '{:.1f} KB'.format(n / 1024.0)
    return '{:.1f} MB'.format(n / 1024.0 / 1024.0)


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
    'theme': 'green',
    'ui_scale': 1.0,
    'show_log': True,
    'last_folder': '',   # 上次选过的音源文件夹，下次「选择音源文件夹」直接从这里开始
}

MIRROR_PLACEHOLDER = '例如 https://ghfast.top'

# 本工具自己的仓库（用于检查软件自身是否有新版本）
APP_REPO = 'Heccdod/lx-music-source-manager'

# 内置多镜像自动回退顺序（当某镜像失效时自动切换下一个，确保国内直链拉取高可用）
MIRROR_FALLBACKS = [
    'https://ghproxy.net',
    'https://gh.llkk.cc',
    'https://gh-proxy.org',
    'https://ghfast.top',
    '',
]

# 热门单音源极速直链（可直接在线拉取到「待导入列表」自选，或一键直接导入）
RECOMMENDED_DIRECT_SOURCES = [
    {
        'id': 'xinghai',
        'name': '星海音乐源 (XingHai)',
        'badge': '★首选推荐',
        'recommended': True,
        'desc': '支持五大平台 128k 至 FLAC / Hi-Res / 母带音质（黄金三件套之一）',
        'raw_url': 'https://raw.githubusercontent.com/pdone/lx-music-source/main/xinghai/latest.js',
        'filename': 'xinghai_latest.js',
    },
    {
        'id': 'hyw',
        'name': 'HYW 公益版',
        'badge': '⚡极速推荐',
        'recommended': True,
        'desc': '下载与连接速度快，推荐与星海搭配使用（黄金三件套之一）',
        'raw_url': 'https://raw.githubusercontent.com/pdone/lx-music-source/main/hyw/latest.js',
        'filename': 'hyw_latest.js',
    },
    {
        'id': 'lx_v7',
        'name': 'LX 官方风格源 (v7)',
        'badge': '🎵经典推荐',
        'recommended': True,
        'desc': '经典高兼容音源，覆盖主流曲库（黄金三件套之一，需洛雪 ≥ v2.6.0）',
        'raw_url': 'https://raw.githubusercontent.com/pdone/lx-music-source/main/lx/latest.js',
        'filename': 'lx_v7_latest.js',
    },
    {
        'id': 'changqing',
        'name': '长青 SVIP 音源 (ChangQing)',
        'badge': '💎无损音质',
        'recommended': False,
        'desc': '支持多平台无损（FLAC）音质解析',
        'raw_url': 'https://raw.githubusercontent.com/pdone/lx-music-source/main/changqing/latest.js',
        'filename': 'changqing_latest.js',
    },
    {
        'id': 'sixyin',
        'name': '六音音源 (SixYin)',
        'badge': '🌸新版适配',
        'recommended': False,
        'desc': '经典六音音源，支持新版客户端（需洛雪桌面版 ≥ v2.6.0）',
        'raw_url': 'https://raw.githubusercontent.com/pdone/lx-music-source/main/sixyin/latest.js',
        'filename': 'sixyin_latest.js',
    },
    {
        'id': 'yuningxi',
        'name': '玉宁熙 Pro 音源 (YuNingXi)',
        'badge': '🎶多平台源',
        'recommended': False,
        'desc': '综合音质好，覆盖主流平台',
        'raw_url': 'https://raw.githubusercontent.com/pdone/lx-music-source/main/yuningxi/latest.js',
        'filename': 'yuningxi_latest.js',
    },
    {
        'id': 'huibq',
        'name': 'Huibq 公益源 (Keep-Alive)',
        'badge': '🛡️稳定试听',
        'recommended': False,
        'desc': '最高 320kbps 稳定在线试听（jsDelivr CDN 直链，请勿高频批量下载防封 IP）',
        'raw_url': 'https://fastly.jsdelivr.net/gh/Huibq/keep-alive/render_api.js',
        'filename': 'huibq_render_api.js',
        'no_mirror': True,
    },
]

# 内置推荐仓库订阅：(显示名, 仓库, 目录, 来源, 一句话说明)
RECOMMENDED_SOURCES = [
    ('guoyue2010 高频维护合集包', 'guoyue2010/lxmusic-', '', 'release', '团队周更/日更 Release 打包源，含星海/轻量并行/墨澜/Hei/V7/HYW/长青，实测剔除失效源'),
    ('pdone 全网最全音源库 (10.8k★)', 'pdone/lx-music-source', '', 'repo', '每日 01:00 自动可用性探测，收录 LX v7/六音/星海/长青/HYW/玉宁熙/Fish 等十余款'),
    ('星海音乐源独立官方仓', 'cdyUuu/lx-music-xinghai-source', '', 'repo', '星海独立官方仓库，五大平台 128k 至 FLAC / Hi-Res / 母带'),
    ('Huibq 经典稳定公益源 (7.7k★)', 'Huibq/keep-alive', '', 'repo', '经典稳定公益源，最高 320k 在线稳定试听'),
    ('wzh15802 汇总归档仓库', 'wzh15802/lxmusic', '', 'repo', '定期汇总洛雪 v7、全豆要聚合 v9.3、长青 SVIP、星海、HYW、六音、野花/野草等'),
    ('星海单源目录订阅 (pdone/xinghai)', 'pdone/lx-music-source', 'xinghai', 'repo', '只订阅 pdone 仓库下的星海音源子目录'),
    ('HYW 公益版目录订阅 (pdone/hyw)', 'pdone/lx-music-source', 'hyw', 'repo', '只订阅 pdone 仓库下的 HYW 音源子目录'),
    ('LX v7 目录订阅 (pdone/lx)', 'pdone/lx-music-source', 'lx', 'repo', '只订阅 pdone 仓库下的 LX v7 音源子目录'),
]


def find_lx_music_path():
    """探测洛雪音乐桌面版主程序，用于「重启洛雪」按钮。"""
    local = os.environ.get('LOCALAPPDATA') or ''
    roaming = os.environ.get('APPDATA') or ''
    candidates = []
    for base in (local, roaming, os.environ.get('ProgramFiles') or '',
                 os.environ.get('ProgramFiles(x86)') or ''):
        if not base:
            continue
        candidates.extend([
            os.path.join(base, 'Programs', 'lx-music-desktop', 'lx-music-desktop.exe'),
            os.path.join(base, 'lx-music-desktop', 'lx-music-desktop.exe'),
            os.path.join(base, 'LX Music', 'lx-music-desktop.exe'),
            os.path.join(base, 'lx-music-desktop', 'LX Music.exe'),
        ])
    for p in candidates:
        if os.path.isfile(p):
            return p
    return ''


def running_lx_music_pids():
    """返回正在运行的洛雪主进程 PID 列表（Windows tasklist 解析）。"""
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq lx-music-desktop.exe', '/FO', 'CSV', '/NH'],
                             capture_output=True, text=True, timeout=15,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        line = line.strip()
        if not line or 'lx-music-desktop' not in line.lower():
            continue
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.append(int(parts[1]))
    return pids


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
    """原子写配置。Windows 上杀毒/索引服务偶尔短暂占用目标文件，
    os.replace 会抛 WinError 5，这里退化为直接覆盖写并重试，避免设置丢失。"""
    p = settings_path()
    os.makedirs(os.path.dirname(p) or '.', exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    for attempt in range(3):
        try:
            os.replace(tmp, p)
            return True
        except PermissionError:
            time.sleep(0.12 * (attempt + 1))
        except OSError:
            break
    try:
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return True
    except OSError:
        return False


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
        self._custom_backup_dir = backup_dir
        self.backup_dir = backup_dir if backup_dir is not None else effective_backup_dir(self.settings)
        self.backups = BackupManager(self.backup_dir)
        self.entries = []
        self.candidates = []
        self.checked_candidates = set()
        self.checked_imported = set()
        self.checked_backups = set()
        self.checked_subs = set()
        self.candidate_filter = ''
        self.import_mode = 'add'
        self.last_folder = self.settings.get('last_folder') or os.path.expanduser('~')
        self.subscriptions = load_subscriptions()
        self._current_sub = None
        self._settings_win = None
        self._dl_state = None
        self._dl_after = None
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

    def _entry_of(self, s):
        """在已导入列表里找到同名音源（normalize_name 比较）。"""
        key = normalize_name(s.name)
        for e in self.entries:
            if normalize_name(e.get('name')) == key:
                return e
        return None

    def _cand_state(self, i):
        """对比待导入音源与已装版本，返回 (mark, color_key, 说明, should_import)。
        mark 用于列表行前缀角标，should_import 供「智能勾选」使用。"""
        s = self.candidates[i]
        e = self._entry_of(s)
        if e is None:
            return ('新', 'accent', '新音源，尚未导入', True)
        old_v = str(e.get('version') or '')
        new_v = str(s.version or '')
        try:
            cmp = version_key(new_v) > version_key(old_v)
            same = version_key(new_v) == version_key(old_v)
        except Exception:
            cmp = new_v != old_v
            same = new_v == old_v
        if same and _same_content(e.get('script'), s.raw):
            return ('=', 'faint', '已装同版，内容一致', False)
        if same:
            return ('↑', 'warn', '版本号相同但脚本内容不同，可覆盖', True)
        if cmp:
            return ('↑', 'green', '可升级：已装 v{}'.format(old_v or '?'), True)
        return ('↓', 'faint', '低于已装 v{}，一般无需导入'.format(old_v or '?'), False)

    def do_smart_select(self):
        """智能勾选：只勾「新音源」和「可升级」，跳过同版和旧版。"""
        picked = 0
        for i in range(len(self.candidates)):
            if not self._candidate_visible(i):
                continue
            if self._cand_state(i)[3]:
                self.checked_candidates.add(i)
                picked += 1
        self._view_refresh_candidates()
        total = sum(1 for i in range(len(self.candidates)) if self._candidate_visible(i))
        if picked:
            self.log('智能勾选：已选中 {} 个需要导入的音源（新音源 / 可升级），跳过 {} 个同版或旧版'.format(
                picked, max(0, total - picked)), 'ok')
        else:
            self.log('智能勾选：当前 {} 个音源都已是同版或更新版本，无需导入'.format(total), 'warn')

    def _toggle_sub(self, i, on):
        """订阅行复选框：勾中表示参与「更新所选」。"""
        if on:
            self.checked_subs.add(i)
        else:
            self.checked_subs.discard(i)
        self._update_sub_buttons()

    def _update_sub_buttons(self):
        btn = getattr(self, 'btn_sub_update', None)
        if btn is None:
            return
        n = len(self.checked_subs)
        try:
            if n:
                btn.configure(text='更新所选({})'.format(n), width=96)
            else:
                btn.configure(text='一键更新', width=76)
        except Exception:
            pass

    def do_select_subs_with_update(self):
        """只勾选检查结果显示「有新版」的订阅。"""
        self.checked_subs = {i for i, s in enumerate(self.subscriptions)
                             if s.get('check_state') == 'new'}
        self._view_refresh_subscriptions()
        self._update_sub_buttons()
        if not self.checked_subs:
            self.log('没有勾中任何订阅：先点「检查更新」看看哪些有新版本', 'warn')
        else:
            self.log('已勾选 {} 个有新版可更新的订阅'.format(len(self.checked_subs)), 'ok')

    def _select_subs_by_state(self, state):
        self.checked_subs = {i for i, s in enumerate(self.subscriptions)
                             if s.get('check_state') == state}
        self._view_refresh_subscriptions()
        self._update_sub_buttons()

    def do_select_all_subs(self, on):
        if on:
            self.checked_subs = set(range(len(self.subscriptions)))
        else:
            self.checked_subs = set()
        self._view_refresh_subscriptions()
        self._update_sub_buttons()

    SEARCH_HINT = '搜索音源名称 / 作者 / 路径…'
    STATUS_HINT = '所有写操作前自动备份 · 备份目录见设置'

    def _on_search(self, _evt=None):
        # 构建界面时占位文字会触发一次 write 回调，此时列表控件还没建好
        if not (hasattr(self, 'cand_list') or hasattr(self, 'cand_tree')):
            return
        text = (self.search_var.get() or '').strip()
        if text == BaseApp.SEARCH_HINT:  # ttk 界面用灰字占位，别把它当成关键词
            text = ''
        self.candidate_filter = text.lower()
        self._view_refresh_candidates()

    def do_scan_folder(self, folder=None):
        if folder is None:
            folder = self._view_ask_folder()
            if not folder:
                return
        self.last_folder = folder
        if self.settings.get('last_folder') != folder:
            self.settings['last_folder'] = folder
            try:
                save_settings(self.settings)
            except Exception:
                pass
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
        # 注意：MODE_UPDATE_LABEL 是「同名更新」，并不以「更新」开头；
        # 早期用 startswith('更新') 判断会导致「同名更新」永远落到 add 分支。
        _v = str(value)
        self.import_mode = 'update' if ('更新' in _v or '同名' in _v) else 'add'
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
        for s, in report['added']:
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
        tk.Button(btns, text='添加', width=10, bg=C['accent'], fg=PALETTE['on_accent'], relief='flat',
                  activebackground=C['accent_hover'], activeforeground=PALETTE['on_accent'], font=f_bold,
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

    def _latest_tag_of(self, sub):
        """只查版本、不下载：release 源读 Release 标签，repo 源读最后一次提交 sha。"""
        if (sub.get('source') or 'release').lower() == 'repo':
            rev, _date = repo_revision(sub['repo'], sub.get('path', ''), sub.get('branch', ''))
            if rev:
                return rev
            _files, ref = fetch_repo_files(sub['repo'], sub.get('path', ''), sub.get('branch', ''))
            return ref or ''
        rel = fetch_latest_release(*sub['repo'].split('/'))
        return rel.get('tag_name', '')

    def do_check_subscriptions(self, quiet=False):
        """只检查不下载：把结果显示到订阅行（有新版 / 已最新），不改变任何本地文件。"""
        if not self.subscriptions:
            if not quiet:
                self._info('提示', '尚未添加任何订阅，请先点「添加订阅」')
            return
        picked = [s for i, s in enumerate(self.subscriptions) if i in self.checked_subs]
        subs = picked or list(self.subscriptions)

        def work():
            out = []
            for sub in subs:
                try:
                    out.append((sub, 'ok', self._latest_tag_of(sub)))
                except Exception as e:
                    out.append((sub, 'err', str(e)))
            return out

        def done(ok, payload):
            if not ok:
                self.log('检查订阅失败：{}'.format(payload), 'error')
                return
            n_new = 0
            for sub, kind, info in payload:
                if kind == 'err':
                    sub['check_state'] = 'error'
                    self.log('「{}」检查失败：{}'.format(sub['repo'], info), 'error')
                elif not info:
                    sub['check_state'] = 'error'
                    self.log('「{}」没有读到版本信息，可能仓库为空或无网络'.format(sub['repo']), 'warn')
                elif sub.get('last_tag') and info == sub.get('last_tag'):
                    sub['check_state'] = 'latest'
                    sub['latest_tag'] = info
                    self.log('「{}」已是最新：{}'.format(sub['repo'], info), 'ok')
                else:
                    sub['check_state'] = 'new'
                    sub['latest_tag'] = info
                    n_new += 1
                    self.log('「{}」发现新版本：最新 {}（本地已用 {}）'.format(
                        sub['repo'], info, sub.get('last_tag') or '无'), 'update')
            self._view_refresh_subscriptions()
            if n_new:
                self.log('检查完成：{} 个订阅可更新，点「一键更新」可批量下载导入'.format(n_new), 'title')
            else:
                self.log('检查完成：全部订阅均为最新版本', 'title')

        self._run_task(work, done, '正在检查全部订阅…（只检查，不下载）')

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
                for s, in report['added']:
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
        picked = [s for i, s in enumerate(self.subscriptions) if i in self.checked_subs]
        subs = picked or list(self.subscriptions)
        if picked:
            head = '更新所选 {} 个订阅？'.format(len(subs))
        else:
            head = '一键订阅更新？（全部 {} 个）'.format(len(subs))
        msg = ('将逐个检查最新版本，发现新版自动下载并以「更新模式」导入。' + chr(10) + chr(10) +
               '· 已是最新的会自动跳过' + chr(10) +
               '· 勾选了「更新所选」时只处理勾中的订阅')
        if not self._confirm(head, msg):
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
                    for s, in report['added']:
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
        # 只留版本 + 作者：描述太长会把左侧名称挤掉（名称被裁成两三个字很难看），
        # 完整描述请看双击详情 / 悬停提示。
        parts = ['v' + str(e.get('version') or '?')]
        if e.get('author'):
            parts.append(short(e['author'], 12))
        return '  ·  '.join(parts)

    def _imp_tip_text(self, e):
        bits = [e.get('name') or '', 'v' + str(e.get('version') or '?')]
        if e.get('author'):
            bits.append('作者：' + e['author'])
        if e.get('description'):
            bits.append(e['description'])
        return ' · '.join([b for b in bits if b])

    def _sub_meta_text(self, sub):
        """订阅第二行：目录 + 版本。检查过之后直接给出「已装 → 最新」的对比。"""
        parts = []
        if (sub.get('source') or 'release') == 'repo':
            parts.append('目录' + ('/' + sub['path'] if sub.get('path') else ''))
        tag = sub.get('last_tag')
        new_tag = sub.get('latest_tag')
        if sub.get('check_state') == 'new' and new_tag:
            parts.append('已装 {} → 最新 {}'.format(tag or '无', new_tag))
        elif sub.get('check_state') == 'latest' and new_tag:
            parts.append('{}（最新）'.format(new_tag))
        else:
            parts.append(tag if tag else '未导入')
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
        if choice == '自定义镜像…':
            custom = self._view_input('设置自定义镜像前缀',
                                      '请输入 GitHub 加速镜像前缀（留空为官方直连）：\n例如：https://ghproxy.net 或 https://gh.llkk.cc')
            if custom is None:
                return
            value = custom.strip()
        elif choice in ('直连', '直连 (官方)'):
            value = ''
        else:
            value = choice
        if getattr(self, 'mirror_entry', None) is not None:
            try:
                self.mirror_entry.delete(0, 'end')
                self.mirror_entry.insert(0, value)
                try:
                    self.mirror_entry.configure(fg=PALETTE['text'])
                except Exception:
                    try:
                        self.mirror_entry.configure(foreground=PALETTE['text'])
                    except Exception:
                        pass
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

    # ---- 下载进度（后台线程只更新 _dl_state，主线程 _poll_dl 负责画到界面） ----
    def _dl_begin(self, label):
        self._dl_state = {'label': label, 'done': 0, 'total': 0, 'active': True, 'text': '准备下载…'}
        self._dl_logged = set()
        if self._dl_after is None:
            try:
                self._dl_after = self.root.after(200, self._dl_tick)
            except Exception:
                self._dl_after = None

    def _dl_update(self, done, total):
        st = getattr(self, '_dl_state', None)
        if not st:
            return
        st['done'] = done
        st['total'] = total
        if total:
            st['text'] = '{}  {:.0%}  ({}/{})'.format(st['label'], min(1.0, done / float(total)),
                                                      human_size(done), human_size(total))
        else:
            st['text'] = '{}  已下载 {}'.format(st['label'], human_size(done))

    def _dl_end(self):
        st = getattr(self, '_dl_state', None)
        if st:
            st['active'] = False

    def _dl_tick(self):
        """主线程定时把下载进度刷到状态栏；没有活动下载时自动停掉定时器。"""
        self._dl_after = None
        st = getattr(self, '_dl_state', None)
        if not st:
            try:
                self._view_set_progress(None, '')
            except Exception:
                pass
            return
        try:
            if st.get('active'):
                total = st['total']
                frac = (st['done'] / float(total)) if total else 0.0
                self._view_set_progress(frac, st['text'])
            else:
                self._view_set_progress(None, '')
        except Exception:
            pass
        if st.get('active'):
            try:
                self._dl_after = self.root.after(200, self._dl_tick)
            except Exception:
                self._dl_after = None

    def _download_url_to(self, url, target):
        """按设置的下载方式把 url 下载到 target，返回实际使用的下载器名。"""
        mode = (self.settings.get('downloader') or 'auto').lower()
        order = {'builtin': ['builtin'], 'idm': ['idm'], 'abdm': ['abdm'],
                 'auto': ['idm', 'abdm', 'builtin']}.get(mode, ['builtin'])
        base = os.path.basename(target)
        for kind in order:
            if kind == 'idm' and self.idm_path:
                try:
                    self.log('用 IDM 下载 {}…'.format(base), 'info')
                    self._dl_begin('IDM 下载 ' + base)
                    self._download_by_idm(url, target)
                    self._dl_end()
                    self.log('IDM 已下载：{}'.format(base), 'ok')
                    return 'idm'
                except FileNotFoundError:
                    self.idm_path = None
                except Exception as e:
                    self._dl_end()
                    self.log('IDM 下载失败（{}），换下一个下载方式'.format(e), 'warn')
                continue
            if kind == 'abdm' and self.abdm_path:
                try:
                    self.log('用 AB Download Manager 下载 {}…'.format(base), 'info')
                    self._dl_begin('ABDM 下载 ' + base)
                    self._download_by_abdm(url, target)
                    self._dl_end()
                    self.log('ABDM 已下载：{}'.format(base), 'ok')
                    return 'abdm'
                except FileNotFoundError:
                    self.abdm_path = None
                except Exception as e:
                    self._dl_end()
                    self.log('ABDM 下载失败（{}），换下一个下载方式'.format(e), 'warn')
                continue
            if kind == 'builtin':
                self.log('开始下载 {}（内置下载器，界面会显示进度）'.format(base), 'info')
                self._dl_begin('下载 ' + base)
                last = [-1]

                def on_prog(done, total, _base=base, _last=last):
                    self._dl_update(done, total)
                    # 每 25% 写一条日志，让人知道确实在下载
                    pct = int((done / float(total)) * 100) if total else 0
                    step = pct // 25
                    if step != _last[0] and step > 0:
                        _last[0] = step
                        self.log('{}：{}%  ({}/{})'.format(_base, pct, human_size(done), human_size(total)), 'info')

                try:
                    size = download_to_file(url, target, on_progress=on_prog)
                    self._dl_end()
                    self.log('下载完成：{}（{}）'.format(base, human_size(size)), 'ok')
                    return 'builtin'
                except Exception as e:
                    self._dl_end()
                    self.log('内置下载失败：{}：{}'.format(base, e), 'error')
                    raise
        # 外部下载器都不可用/失败时用内置兜底
        self.log('开始下载 {}（内置下载器兜底）'.format(base), 'info')
        self._dl_begin('下载 ' + base)
        try:
            size = download_to_file(url, target, on_progress=self._dl_update)
            self._dl_end()
            self.log('下载完成：{}（{}）'.format(base, human_size(size)), 'ok')
            return 'builtin'
        except Exception:
            self._dl_end()
            raise

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
                dirs2[:] = sorted(d for d in dirs2 if d != 'history')
                for fn in sorted(files2):
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
        parsed = []
        for p in items:
            try:
                with open(p, 'rb') as f:
                    content = f.read()
                text, enc = decode_script_bytes(content)
                meta = parse_script_meta(text, fallback_name=os.path.splitext(os.path.basename(p))[0])
            except Exception:
                continue
            parsed.append((p, text, meta, enc))
        # 同一个压缩包内可能包含同名音源的多个版本：只保留版本号最高的那个，避免越更新版本越低
        best = {}
        for item in parsed:
            key = normalize_name(item[2].get('name', ''))
            prev = best.get(key)
            if prev is None or version_key(item[2].get('version')) >= version_key(prev[2].get('version')):
                best[key] = item
        scripts = []
        for p, text, meta, enc in sorted(best.values(), key=lambda it: it[2].get('name', '')):
            scripts.append(SourceScript(p, os.path.relpath(p, subdir), text, meta, enc,
                                        not _block_comment(text)))
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
        """单击订阅：把该订阅已下载的最新音源刷新进「待导入音源」列表；若未下载则引导拉取挑选。"""
        self._current_sub = sub.get('repo')
        self._view_refresh_subscriptions()
        d = self._sub_download_dir(sub)
        has_js = False
        if os.path.isdir(d):
            for _r, dirs2, files2 in os.walk(d):
                dirs2[:] = [x for x in dirs2 if x != 'history']
                if any(fn.lower().endswith('.js') for fn in files2):
                    has_js = True
                    break
        if not has_js:
            if self._confirm('拉取订阅音源供挑选？',
                             '订阅「{}」尚未下载到本地。\n\n'
                             '是否立即拉取该订阅的最新音源到左侧「待导入音源」列表？\n'
                             '（拉取后不会强制全部导入，您可以自由勾选想要的音源再导入）'.format(sub.get('repo'))):
                self.do_fetch_sub_to_candidates(sub)
            return
        res = self._load_sub_sources(sub, silent=True)
        if res is None:
            return
        added, removed = res
        self.do_smart_select()
        self.log('订阅「{}」：已加载 {} 个本地音源到左侧「待导入音源」（并已为您智能勾选推荐项）'.format(
            sub['repo'], added), 'ok' if added else 'warn')

    def do_fetch_sub_to_candidates(self, sub=None):
        """只拉取订阅的最新音源到左侧「待导入音源」列表并智能勾选，不直接写入 user_api.json！
        解决用户痛点：合集包里有十几个音源，用户只想拉下来自己挑哪几个导入。"""
        if sub is not None:
            subs = [sub]
        else:
            if not self.subscriptions:
                self._info('提示', '尚未添加任何订阅，请先点「★ 精选源库」或「+ 添加」')
                return
            picked = [s for i, s in enumerate(self.subscriptions) if i in self.checked_subs]
            subs = picked or list(self.subscriptions)

        def work():
            out = []
            for s in subs:
                try:
                    subdir = self._sub_download_dir(s)
                    has_local_js = False
                    if os.path.isdir(subdir):
                        for _r, d2, f2 in os.walk(subdir):
                            d2[:] = [x for x in d2 if x != 'history']
                            if any(fn.lower().endswith('.js') for fn in f2):
                                has_local_js = True
                                break
                    # 如果本地还没有任何 .js，临时清空 last_tag 以强制拉取下来
                    saved_tag = s.get('last_tag')
                    if not has_local_js:
                        s['last_tag'] = ''
                    try:
                        kind, tag, sdir, items = self._fetch_sub_update(s)
                    finally:
                        s['last_tag'] = saved_tag
                    out.append((s, kind, tag, sdir, items))
                except Exception as e:
                    out.append((s, 'err', str(e), None, None))
            return out

        def done(ok, payload):
            if not ok:
                self.log('拉取订阅音源失败：{}'.format(payload), 'error')
                return
            total_loaded = 0
            for s, kind, tag, sdir, items in payload:
                if kind == 'err':
                    self.log('「{}」拉取失败：{}'.format(s['repo'], tag), 'error')
                    continue
                if kind == 'noasset':
                    self.log('「{}」没有找到 .js / .zip 音源附件'.format(s['repo']), 'warn')
                    continue
                if kind == 'new' and items:
                    try:
                        for target, name in items:
                            self._extract_asset_main(target, name,
                                                     'github:{}#{}'.format(s['repo'], tag), sdir)
                        s['last_tag'] = tag
                        s['latest_tag'] = tag
                        s['check_state'] = 'latest'
                    except Exception as e:
                        self.log('「{}」解压失败：{}'.format(s['repo'], e), 'error')
                        continue
                else:
                    s['check_state'] = 'latest'
                self._current_sub = s.get('repo')
                res = self._load_sub_sources(s, silent=True)
                if res:
                    total_loaded += res[0]
            save_subscriptions(self.subscriptions)
            self._view_refresh_subscriptions()
            if self.candidates:
                self.do_smart_select()
            self.log('已拉取并载入 {} 个音源到左侧「待导入音源」列表（未直接写入洛雪），请勾选想要的音源后点击「导入所选」！'.format(
                len(self.candidates)), 'title')

        label = '正在拉取「{}」到待导入列表…'.format(subs[0]['repo']) if len(subs) == 1 else '正在拉取 {} 个订阅到待导入列表…'.format(len(subs))
        self._run_task(work, done, label)

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
        self.candidates.append(SourceScript(path, rel, text, meta, enc, not _block_comment(text)))
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
        # 订阅右键：拉取挑选 / 直接更新导入 / 载入本地 / 打开目录 / 删除
        if not (0 <= i < len(self.subscriptions)):
            return
        sub = self.subscriptions[i]
        self._popup_menu(event, [
            ('📥 拉取最新到「待导入音源」自由挑选', lambda: self.do_fetch_sub_to_candidates(sub)),
            ('⚡ 立即下载并直接更新到洛雪', lambda: self.do_update_subscription(sub)),
            ('📂 载入本地已下载音源', lambda: self.do_show_subscription_sources(sub)),
            None,
            ('打开下载目录', lambda: self.do_open_download_dir(sub)),
            ('删除订阅', lambda: self.do_delete_subscription(sub)),
        ])

    def do_open_download_dir(self, sub=None):
        d = self._sub_download_dir(sub) if sub else effective_download_dir(self.settings)
        self._open_dir(d)

    # ---------------- 洛雪重启 ----------------
    def do_restart_lx_music(self):
        """重启洛雪音乐，让刚导入的音源立即生效。"""
        exe = self.settings.get('lx_path') or find_lx_music_path()
        pids = running_lx_music_pids()
        if not exe and not pids:
            self._info('未找到洛雪音乐',
                       '没有探测到洛雪音乐桌面版。\n\n'
                       '请先启动洛雪音乐，或在「偏好设置」里点「选择洛雪程序」手动指定 lx-music-desktop.exe。')
            return
        if pids:
            if not self._confirm('重启洛雪音乐？',
                                 '将关闭正在运行的洛雪音乐（进程数 {}）并重新启动，\n'
                                 '以便让刚导入的音源立即生效。\n\n'
                                 '如果洛雪里还有未保存的操作，请先取消并手动保存。'.format(len(pids))):
                return
            for pid in pids:
                try:
                    subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True, timeout=15,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                except Exception:
                    pass
            time.sleep(1.2)
        if not exe:
            self.log('已关闭洛雪音乐，但没有找到程序路径，请手动启动一次', 'warn')
            self._info('已关闭洛雪音乐', '已关闭洛雪音乐，但没找到程序所在路径。\n\n请在「偏好设置」里点「选择洛雪程序」指定一次，之后就能一键重启。')
            return
        try:
            subprocess.Popen([exe], close_fds=True)
            self.log('已重启洛雪音乐，音源已生效：{}'.format(exe), 'ok')
        except Exception as e:
            self.log('启动洛雪音乐失败：{}'.format(e), 'error')
            self._info('启动失败', '无法启动：{}\n\n{}'.format(exe, e))

    # ---------------- 外观：主题 / 字号（即时无感热切换，无需重启应用） ----------------
    def do_set_theme(self, name):
        name = name if name in THEMES else 'green'
        if name == self.settings.get('theme') and PALETTE.get('bg') == THEMES[name]['bg']:
            return
        self.settings['theme'] = name
        save_settings(self.settings)
        apply_theme(name)
        self._view_rebuild_live()
        self.log('已实时切换主题配色：{}'.format(THEMES[name]['label']), 'ok')

    def do_set_ui_scale(self, value):
        v = _ui_scale(value, self.settings.get('ui_scale', 1.0))
        if abs(v - float(self.settings.get('ui_scale') or 1.0)) < 0.01:
            return
        self.settings['ui_scale'] = v
        save_settings(self.settings)
        self._view_rebuild_live()
        self.log('界面字号已实时调整为 {:.0%}'.format(v), 'ok')

    def _view_rebuild_live(self):
        """由子类实现的界面热重建钩子（切换主题/字号无需重启进程）。"""
        pass

    def _ask_relaunch(self, what):
        self._view_rebuild_live()

    def relaunch_app(self):
        """重启本工具自身（保留命令行参数与环境）。"""
        try:
            exe = sys.executable
            args = [exe] + (sys.argv if getattr(sys, 'frozen', False) else [os.path.abspath(__file__)] + sys.argv[1:])
            subprocess.Popen(args, close_fds=True)
        except Exception as e:
            self.log('重启失败：{}'.format(e), 'error')
            self._info('重启失败', '无法自动重启：{}\n\n请手动关闭并重新打开工具。'.format(e))
            return
        try:
            self.root.destroy()
        except Exception:
            pass

    def set_lx_music_path(self):
        p = filedialog.askopenfilename(parent=self.root, title='选择 lx-music-desktop.exe',
                                       filetypes=[('程序', '*.exe'), ('全部文件', '*.*')])
        if not p:
            return
        self.settings['lx_path'] = p
        save_settings(self.settings)
        self.log('已指定洛雪音乐程序：{}'.format(p), 'ok')
        self._view_refresh_settings_row()

    # ---------------- 软件自身更新 ----------------
    def do_check_app_update(self):
        """检查本工具是否有新版本（GitHub Release），不涉及音源订阅。"""
        self.log('正在检查工具自身更新（{}）…'.format(APP_REPO), 'info')

        def work():
            owner, name = parse_repo_ref(APP_REPO)
            rel = fetch_latest_release(owner, name)
            return rel

        def done(ok, payload):
            if not ok:
                self._info('检查更新失败', '无法读取发布信息：\n\n{}\n\n当前版本：v{}'.format(payload, __version__))
                self.log('检查工具更新失败：{}'.format(payload), 'error')
                return
            latest = (payload.get('tag_name') or '').strip()
            try:
                newer = version_key(latest) > version_key(__version__)
            except Exception:
                newer = latest.lstrip('vV') != __version__
            if not newer:
                self._info('已是最新版本', '当前版本 v{} 已是最新。\n\n最新发布：{}'.format(__version__, latest or '?'))
                self.log('工具已是最新版本：v{}'.format(__version__), 'ok')
                return
            body = (payload.get('body') or '').strip()
            assets = [a for a in (payload.get('assets') or [])
                      if a.get('name', '').lower().endswith('.exe')]
            lines = ['发现新版本：{}（当前 v{}）'.format(latest, __version__), '']
            if body:
                lines.append(short(body, 600))
                lines.append('')
            if assets:
                lines.append('可直接下载：{}'.format(assets[0]['name']))
            else:
                lines.append('该版本没有 .exe 附件，将打开 GitHub 发布页。')
            if self._confirm('发现新版本 ' + latest, '\n'.join(lines)):
                if assets:
                    self._download_app_release(assets[0], latest)
                else:
                    webbrowser.open(payload.get('html_url') or 'https://github.com/' + APP_REPO + '/releases/latest')

        self._run_task(work, done, '正在检查工具自身更新…')

    def _download_app_release(self, asset, tag):
        folder = self.settings.get('download_dir') or effective_download_dir(self.settings)
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception:
            pass
        target = os.path.join(folder, asset.get('name') or 'update.exe')
        if os.path.exists(target):
            try:
                os.remove(target)
            except OSError:
                pass

        def work():
            self._download_url_to(asset['browser_download_url'], target)
            return target

        def done(ok, payload):
            if not ok:
                self._info('下载失败', '下载新版本失败：\n\n{}'.format(payload))
                return
            self.log('新版本已下载：{}'.format(payload), 'ok')
            if self._confirm('下载完成', '新版本已下载到：\n\n{}\n\n是否打开所在文件夹？'.format(payload)):
                self._open_dir(os.path.dirname(payload))

        self._run_task(work, done, '正在下载新版本 {}…'.format(tag))

    # ---------------- 官方精选音源库（热门单源直链多镜像加速 + 活跃仓库一键订阅） ----------------
    def _is_recommended_subscribed(self, repo, path):
        return any(s.get('repo') == repo and (s.get('path') or '') == path
                   for s in self.subscriptions)

    def _download_direct_with_fallback(self, item, dest_dir):
        """带多镜像自动回退的单音源下载：当前镜像 -> ghproxy.net -> gh.llkk.cc -> gh-proxy.org -> ghfast.top -> 直连。"""
        os.makedirs(dest_dir, exist_ok=True)
        target = os.path.join(dest_dir, item['filename'])
        raw_url = item['raw_url']
        if item.get('no_mirror'):
            urls = [raw_url, raw_url.replace('fastly.jsdelivr.net', 'cdn.jsdelivr.net'),
                    raw_url.replace('fastly.jsdelivr.net', 'gcore.jsdelivr.net')]
        else:
            cur = get_mirror()
            prefixes = ([cur] if cur else []) + [m for m in MIRROR_FALLBACKS if m != cur]
            urls = [(p.rstrip('/') + '/' + raw_url if p else raw_url) for p in prefixes]
        last_err = None
        for u in urls:
            try:
                self._dl_begin('拉取 ' + item['name'])
                download_to_file(u, target, on_progress=self._dl_update, timeout=20)
                self._dl_end()
                if os.path.isfile(target) and os.path.getsize(target) > 32:
                    return target
            except Exception as e:
                self._dl_end()
                last_err = e
                continue
        raise ConnectionError('所有加速镜像均拉取失败：{}'.format(last_err or '网络超时'))

    def do_fetch_direct_sources(self, direct_ids, auto_import=False):
        """拉取选中的热门单音源直链：
        auto_import=False → 放入左侧「待导入音源」并自动智能勾选（供用户挑选）；
        auto_import=True  → 自动备份并直接写入 user_api.json。"""
        items = [it for it in RECOMMENDED_DIRECT_SOURCES if it['id'] in direct_ids]
        if not items:
            self._info('提示', '请至少勾选一个热门单音源')
            return
        dest_dir = os.path.join(effective_download_dir(self.settings), 'recommended_direct')

        def work():
            ok_paths = []
            errs = []
            for it in items:
                try:
                    p = self._download_direct_with_fallback(it, dest_dir)
                    ok_paths.append((it, p))
                except Exception as e:
                    errs.append((it['name'], str(e)))
            return (ok_paths, errs)

        def done(ok, payload):
            if not ok:
                self.log('精选单音源拉取失败：{}'.format(payload), 'error')
                return
            ok_paths, errs = payload
            for name, err in errs:
                self.log('拉取「{}」失败：{}'.format(name, err), 'error')
            scripts = []
            for it, p in ok_paths:
                try:
                    text, enc = read_text_auto(p)
                    meta = parse_script_meta(text, fallback_name=it['name'])
                    scripts.append(SourceScript(p, os.path.basename(p), text, meta, enc, not _block_comment(text)))
                except Exception as e:
                    self.log('解析「{}」失败：{}'.format(it['name'], e), 'error')
            if not scripts:
                return
            if auto_import:
                if not self._auto_backup():
                    return
                report = apply_imports(self.entries, scripts, 'update')
                if not self._save_entries('写入 user_api.json'):
                    return
                for s, old_v, new_v in report['updated']:
                    self.log('更新：{}  v{} → v{}'.format(s.name, old_v, new_v), 'update')
                for s, in report['added']:
                    self.log('新增：{}  v{}'.format(s.name, s.version), 'ok')
                for s, reason in report['skipped']:
                    self.log('跳过：{}（{}）'.format(s.name, reason), 'warn')
                self._view_refresh_imported()
                self._view_status()
                self.log('精选单音源一键导入完成（新增 {} / 更新 {} / 跳过 {}），点顶栏「重启洛雪」立即生效！'.format(
                    len(report['added']), len(report['updated']), len(report['skipped'])), 'title')
            else:
                existing = {os.path.normcase(os.path.abspath(s.path)): idx
                            for idx, s in enumerate(self.candidates)}
                for s in scripts:
                    k = os.path.normcase(os.path.abspath(s.path))
                    if k in existing:
                        self.candidates[existing[k]] = s
                    else:
                        self.candidates.append(s)
                self._view_refresh_candidates()
                self.do_smart_select()
                self.log('已将 {} 个精选单音源拉取到左侧「待导入音源」，并已为您智能勾选，请确认后点击「导入所选」！'.format(
                    len(scripts)), 'title')

        self._run_task(work, done, '正在通过加速直链拉取 {} 个精选音源…'.format(len(items)))

    def do_add_recommended(self):
        """打开「★ 官方精选音源库」窗口：支持极速拉取 7 大热门单源（自选/直导）与订阅 5 大活跃仓库。"""
        res = self._view_pick_recommended()
        if not res:
            return
        if isinstance(res, list):
            # 兼容单元测试直接返回索引列表的情形
            repo_indices = res
            action = 'sub_repos'
            direct_ids = []
        else:
            action = res.get('action')
            direct_ids = res.get('direct_ids') or []
            repo_indices = res.get('repo_indices') or []

        if action in ('fetch_direct_cand', 'fetch_direct_import'):
            self.do_fetch_direct_sources(direct_ids, auto_import=(action == 'fetch_direct_import'))
            return

        if action == 'sub_repos':
            if not repo_indices:
                return
            added = 0
            new_subs = []
            for idx in repo_indices:
                label, repo, path, src, _note = RECOMMENDED_SOURCES[idx]
                if self._is_recommended_subscribed(repo, path):
                    continue
                sub_obj = {
                    'repo': repo, 'name': label, 'last_tag': '', 'source': src,
                    'path': path, 'branch': '',
                    'added_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                }
                self.subscriptions.append(sub_obj)
                new_subs.append(sub_obj)
                added += 1
                self.log('加入推荐订阅：{}（{}）'.format(label, repo), 'ok')
            if not added:
                self._info('提示', '选中的推荐仓库都已经在订阅列表里了')
                return
            save_subscriptions(self.subscriptions)
            self._view_refresh_subscriptions()
            self.log('已加入 {} 个推荐仓库订阅，正在检查可用版本…'.format(added), 'ok')
            self.do_check_subscriptions(quiet=True)

    def _view_pick_recommended(self):
        """官方精选音源库弹窗：
        上半区：7 大热门单音源加速直链（默认勾选黄金三件套：星海 + HYW + LX v7），支持「拉取到待导入挑选」或「直接导入」；
        下半区：主流 GitHub 活跃音源仓库（含 guoyue2010/lxmusic-、pdone 等），支持一键加入订阅。"""
        C = self.C
        dlg = tk.Toplevel(self.root)
        dlg.title('★ 官方精选音源库 — 极速直链与活跃仓库')
        dlg.configure(bg=C['bg'])
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.grid_columnconfigure(0, weight=1)
        dlg.grid_rowconfigure(1, weight=1)

        head = tk.Frame(dlg, bg=C['card'], highlightthickness=1, highlightbackground=C.get('card_border', C['border']))
        head.grid(row=0, column=0, sticky='ew', padx=14, pady=(12, 6))
        tk.Label(head, text='★ 官方精选音源库（内置多镜像自动加速）', bg=C['card'], fg=C['text'],
                 font=self.f_card, anchor='w').pack(fill='x', padx=16, pady=(10, 2))
        tk.Label(head, text='💡 黄金搭配建议：优先导入「星海 + HYW + LX v7」三件套，覆盖绝大多数曲库与无损音质；六音/星海/v7 要求洛雪 ≥ v2.6.0；公益源请勿高频批量下载歌单以防封 IP。',
                 bg=C['card'], fg=C['muted'], font=self.f_tiny, anchor='w', justify='left',
                 wraplength=int(720 * self.ui_scale)).pack(fill='x', padx=16, pady=(0, 10))

        holder = tk.Frame(dlg, bg=C['card'], highlightthickness=1, highlightbackground=C.get('card_border', C['border']))
        holder.grid(row=1, column=0, sticky='nsew', padx=14, pady=4)
        canvas = tk.Canvas(holder, bg=C['card'], highlightthickness=0, bd=0)
        sb = tk.Scrollbar(holder, orient='vertical', command=canvas.yview,
                          bg=C['card'], troughcolor=C['field'], activebackground=C['border'],
                          width=12, relief='flat', bd=0)
        inner = tk.Frame(canvas, bg=C['card'])
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side='left', fill='both', expand=True, padx=(6, 0), pady=6)
        sb.pack(side='right', fill='y', pady=6)
        win = canvas.create_window((0, 0), window=inner, anchor='nw')

        def _fit(_e=None):
            canvas.configure(scrollregion=canvas.bbox('all'))
            canvas.itemconfigure(win, width=canvas.winfo_width())
        inner.bind('<Configure>', _fit)
        canvas.bind('<Configure>', _fit)

        def _wheel(e):
            canvas.yview_scroll(int(-e.delta / 120), 'units')
        canvas.bind('<MouseWheel>', _wheel)
        inner.bind('<MouseWheel>', _wheel)

        # ---- 分组一：热门单音源在线极速直链 ----
        sec1 = tk.Frame(inner, bg=C['field'])
        sec1.pack(fill='x', padx=8, pady=(4, 4))
        tk.Label(sec1, text='一、热门单音源极速直链（已默认勾选黄金三件套，自动多镜像回退下载）',
                 bg=C['field'], fg=C['accent'], font=self.f_bold, anchor='w').pack(fill='x', padx=10, pady=6)

        direct_vars = {}
        for item in RECOMMENDED_DIRECT_SOURCES:
            var = tk.BooleanVar(value=bool(item.get('recommended')))
            direct_vars[item['id']] = var
            row = tk.Frame(inner, bg=C['card'], cursor='hand2')
            row.pack(fill='x', padx=10, pady=2)
            chk = WebCheck(row, variable=var, size=18, colors=C)
            chk.pack(side='left', padx=(6, 6), pady=5)
            badge = tk.Label(row, text=item['badge'], bg=C['card2'], fg=C['accent'],
                             font=self.f_tiny, padx=6, pady=1)
            badge.pack(side='left', padx=(0, 8), pady=5)
            name_l = tk.Label(row, text=item['name'], bg=C['card'], fg=C['text'],
                              font=self.f_bold, anchor='w')
            name_l.pack(side='left', padx=(0, 8))
            desc_l = tk.Label(row, text=item['desc'], bg=C['card'], fg=C['muted'],
                              font=self.f_tiny, anchor='w')
            desc_l.pack(side='left', fill='x', expand=True)
            for w in (row, badge, name_l, desc_l):
                w.bind('<Button-1>', lambda _e, v=var: v.set(not v.get()))
                w.bind('<MouseWheel>', _wheel)

        # ---- 分组二：主流活跃 GitHub 仓库订阅 ----
        sec2 = tk.Frame(inner, bg=C['field'])
        sec2.pack(fill='x', padx=8, pady=(12, 4))
        tk.Label(sec2, text='二、主流活跃 GitHub 音源仓库（加入「订阅更新」长期跟进新版本）',
                 bg=C['field'], fg=C['text'], font=self.f_bold, anchor='w').pack(fill='x', padx=10, pady=6)

        vars_map = {}
        for i, (label, repo, path, src, note) in enumerate(RECOMMENDED_SOURCES):
            already = self._is_recommended_subscribed(repo, path)
            var = tk.BooleanVar(value=(i < 2 and not already))
            vars_map[i] = var
            row = tk.Frame(inner, bg=C['card'], cursor='hand2')
            row.pack(fill='x', padx=10, pady=2)
            WebCheck(row, variable=var, size=18, colors=C).pack(side='left', padx=(6, 6), pady=5)
            tag_txt = 'Release整包' if src == 'release' else '仓库目录'
            badge = tk.Label(row, text=tag_txt, bg=C['field'], fg=C['muted'],
                             font=self.f_tiny, padx=6, pady=1)
            badge.pack(side='left', padx=(0, 8), pady=5)
            name_l = tk.Label(row, text=label + (' (已订阅)' if already else ''), bg=C['card'],
                              fg=C['faint'] if already else C['text'], font=self.f_bold, anchor='w')
            name_l.pack(side='left', padx=(0, 8))
            desc_l = tk.Label(row, text='{} · {}'.format(repo + ('/' + path if path else ''), note),
                              bg=C['card'], fg=C['faint'], font=self.f_tiny, anchor='w')
            desc_l.pack(side='left', fill='x', expand=True)
            for w in (row, badge, name_l, desc_l):
                w.bind('<Button-1>', lambda _e, v=var: v.set(not v.get()))
                w.bind('<MouseWheel>', _wheel)

        def mkbtn(parent, text, cmd, primary=False, secondary=False):
            bg = C['accent'] if primary else (C['card2'] if secondary else C['card'])
            fg = C['on_accent'] if primary else (C['accent'] if secondary else C['text'])
            abg = C['accent_hover'] if primary else C['hover']
            return tk.Button(parent, text=text, command=cmd, font=self.f_btn, relief='flat', bd=0,
                             padx=14, pady=6, cursor='hand2', bg=bg, fg=fg,
                             activebackground=abg, activeforeground=fg,
                             highlightthickness=0 if (primary or secondary) else 1,
                             highlightbackground=C['border'])

        result = {'v': None}

        def do_act(action_name):
            result['v'] = {
                'action': action_name,
                'direct_ids': [k for k, v in direct_vars.items() if v.get()],
                'repo_indices': [i for i, v in vars_map.items() if v.get()],
            }
            dlg.destroy()

        bar = tk.Frame(dlg, bg=C['bg'])
        bar.grid(row=2, column=0, sticky='ew', padx=14, pady=(6, 12))
        mkbtn(bar, '黄金三件套', lambda: [v.set(k in ('xinghai', 'hyw', 'lx_v7')) for k, v in direct_vars.items()]).pack(side='left', padx=(0, 6))
        mkbtn(bar, '全选单源', lambda: [v.set(True) for v in direct_vars.values()]).pack(side='left', padx=(0, 6))
        mkbtn(bar, '取消', dlg.destroy).pack(side='right', padx=(6, 0))
        mkbtn(bar, '➕ 订阅所选仓库', lambda: do_act('sub_repos'), secondary=True).pack(side='right', padx=4)
        mkbtn(bar, '⚡ 直接导入所选单源', lambda: do_act('fetch_direct_import'), secondary=True).pack(side='right', padx=4)
        mkbtn(bar, '📥 拉取所选单源到待导入列表 (推荐)', lambda: do_act('fetch_direct_cand'), primary=True).pack(side='right', padx=4)

        dlg.protocol('WM_DELETE_WINDOW', dlg.destroy)
        dlg.update_idletasks()
        try:
            w = min(int(820 * self.ui_scale), self.root.winfo_screenwidth() - 80)
            h = min(int(640 * self.ui_scale), self.root.winfo_screenheight() - 80)
            x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - w) // 2)
            y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - h) // 3)
            dlg.geometry('{}x{}+{}+{}'.format(w, h, x, y))
        except Exception:
            dlg.geometry('800x620')
        dlg.wait_window()
        return result['v']
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
            self.backup_dir = (self._custom_backup_dir if getattr(self, '_custom_backup_dir', None)
                               else effective_backup_dir(self.settings))
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

    def _view_set_progress(self, frac, text):
        """在状态栏显示进度；frac 为 None 表示隐藏进度。"""
        pass

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
    """返回带惯性平滑滚动的 CTkScrollableFrame 子类（60fps 丝滑滚动，无拖尾）。"""
    global _SMOOTH_FRAME_CLASS
    if _SMOOTH_FRAME_CLASS is not None:
        return _SMOOTH_FRAME_CLASS
    import customtkinter as ctk

    class SmoothScrollableFrame(ctk.CTkScrollableFrame):
        FRAME_MS = 16

        def __init__(self, *args, **kwargs):
            self._smooth_vel = 0.0
            self._smooth_after = None
            self._fit_after = None
            self._sr_after = None
            self._last_canvas_sz = None
            self._empty_mode = False
            super().__init__(*args, **kwargs)
            # 替换 CTkScrollableFrame 默认在每个像素缩放时同步触发的重排绑定，消除窗口拖拽缩放卡顿
            try:
                self.unbind('<Configure>')
                self._parent_canvas.unbind('<Configure>')
                self.bind('<Configure>', self._on_inner_configure_throttled)
                self._parent_canvas.bind('<Configure>', self._on_canvas_configure_throttled)
                # 同样为外层 _parent_frame 的圆角重绘增加缩放节流
                pf = getattr(self, '_parent_frame', None)
                if pf is not None:
                    _throttle_ctk_frame_redraw(pf)
            except Exception:
                pass

        def set_empty_mode(self, is_empty):
            """空状态模式下将内部 Frame 宽高撑满整个 Canvas，使空态提示框能水平+垂直正居中。"""
            self._empty_mode = bool(is_empty)
            self._last_canvas_sz = None
            if self._fit_after is None:
                self._fit_after = self.after(10, self._flush_canvas_fit)

        def _on_inner_configure_throttled(self, _event=None):
            if self._sr_after is None:
                self._sr_after = self.after(40, self._flush_scrollregion)

        def _flush_scrollregion(self):
            self._sr_after = None
            try:
                if self._parent_canvas.winfo_exists():
                    if self._empty_mode:
                        cw = max(1, self._parent_canvas.winfo_width())
                        ch = max(1, self._parent_canvas.winfo_height())
                        self._parent_canvas.configure(scrollregion=(0, 0, cw, ch))
                    else:
                        self._parent_canvas.configure(scrollregion=self._parent_canvas.bbox('all'))
            except Exception:
                pass

        def _on_canvas_configure_throttled(self, event):
            sz = (getattr(event, 'width', 0), getattr(event, 'height', 0))
            if sz == self._last_canvas_sz:
                return
            self._last_canvas_sz = sz
            if self._fit_after is None:
                self._fit_after = self.after(32, self._flush_canvas_fit)

        def _flush_canvas_fit(self):
            self._fit_after = None
            try:
                if self._parent_canvas.winfo_exists():
                    cw = self._parent_canvas.winfo_width()
                    ch = self._parent_canvas.winfo_height()
                    if cw > 1:
                        if self._empty_mode and ch > 1:
                            self._parent_canvas.itemconfigure(self._create_window_id, width=cw, height=ch)
                            self._parent_canvas.configure(scrollregion=(0, 0, cw, ch))
                        else:
                            self._parent_canvas.itemconfigure(self._create_window_id, width=cw, height=0)
            except Exception:
                pass

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
            self._smooth_vel += -event.delta / 120.0 * 7.5
            self._smooth_start()

        def _smooth_start(self):
            if self._smooth_after is None:
                self._smooth_after = self.after(self.FRAME_MS, self._smooth_step)

        def _smooth_step(self):
            self._smooth_after = None
            self._smooth_vel *= 0.78
            if abs(self._smooth_vel) < 0.4:
                self._smooth_vel = 0.0
                return
            step = self._smooth_vel
            if abs(step) < 2:
                step = 2 if step > 0 else -2
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
            for attr in ('_smooth_after', '_fit_after', '_sr_after'):
                tid = getattr(self, attr, None)
                if tid is not None:
                    try:
                        self.after_cancel(tid)
                    except Exception:
                        pass
            super().destroy()

    _SMOOTH_FRAME_CLASS = SmoothScrollableFrame
    return _SMOOTH_FRAME_CLASS


def _throttle_ctk_frame_redraw(frame, delay_ms=42):
    """为大尺寸 CTkFrame 卡片的 <Configure> 重绘增加防抖节流，消除窗口拖拽缩放或全屏时的 Canvas 逐像素重绘卡顿。"""
    try:
        frame._redraw_after_id = None
        frame._pending_wh = None

        def _flush_draw():
            frame._redraw_after_id = None
            wh = frame._pending_wh
            if wh is None:
                return
            try:
                if frame.winfo_exists():
                    frame._current_width, frame._current_height = wh
                    frame._draw(no_color_updates=True)
            except Exception:
                pass

        def _throttled_dim_event(event):
            w = frame._reverse_widget_scaling(event.width)
            h = frame._reverse_widget_scaling(event.height)
            if round(frame._current_width) == round(w) and round(frame._current_height) == round(h):
                return
            # 首次布局直接绘制，后续缩放防抖
            if frame._current_width <= 200 and frame._current_height <= 200:
                frame._current_width, frame._current_height = w, h
                frame._draw(no_color_updates=True)
                return
            frame._pending_wh = (w, h)
            if frame._redraw_after_id is None:
                frame._redraw_after_id = frame.after(delay_ms, _flush_draw)

        tk.Frame.bind(frame, '<Configure>', _throttled_dim_event)
    except Exception:
        pass


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
        _s = load_settings()
        apply_theme(_s.get('theme') or 'green')
        self.C = PALETTE
        self.dpi_scale = _dpi_scale()
        self.ui_scale = _ui_scale(_s.get('ui_scale')) * self.dpi_scale
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
        self._hidden = hidden
        self._is_maximized = False
        self._normal_geom = None
        self._hwnd = None
        self.SmoothFrame = smooth_scrollable_class()
        self.settings = _s
        set_mirror(self.settings['mirror'])
        self.use_idm = self.settings['use_idm']
        self.idm_path = find_idm_path()
        self.abdm_path = self.settings.get('abdm_path') or find_abdm_path()
        dark = (self.settings.get('theme') or 'green') == 'dark'
        ctk.set_appearance_mode('dark' if dark else 'light')
        ctk.set_default_color_theme('blue')
        self.root = ctk.CTk(fg_color=self.C['bg'])
        _ensure_claude_fonts(self.root)
        if hidden:
            self.root.withdraw()
        self.root.title(APP_TITLE)
        w, h = _initial_size(self.ui_scale)
        self.root.geometry('{}x{}'.format(w, h))
        _mw, _mh = _min_size(self.ui_scale)
        self.root.minsize(_mw, _mh)
        self.icon = _make_icon(zoom=2, theme='green')
        self._icon_small = _make_icon(zoom=1)
        _apply_taskbar_and_window_icon(self.root, self.icon)
        self.path_label = None
        self.folder_label = None
        self.mirror_entry = None
        self._resize_after = None
        self._last_root_size = None
        self._active_popover = None
        self._hovered_cand = None
        self._hovered_imp = None
        self._hovered_sub = None
        self._drag_offset = None
        self._effective_scale = self.ui_scale
        self._setup_frameless_window()
        self._build()
        super().__init__(user_api_path=user_api_path, backup_dir=backup_dir, auto_confirm=auto_confirm)
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)
        # 使用专属 RootOnly bindtag，避免数千个子控件每次重排都冒泡触发 Python 回调
        try:
            self.root.bindtags(('RootOnly',) + self.root.bindtags())
            self.root.bind_class('RootOnly', '<Configure>', self._on_root_configure)
        except Exception:
            self.root.bind('<Configure>', self._on_root_configure)
        self.root.bind('<Button-1>', self._on_root_click, add='+')

    # ---------------- 无原生标题栏一体化窗口控制 (Win32 WS_CAPTION 移除 + SetWindowPos 丝滑拖拽) ----------------
    def _setup_frameless_window(self):
        """移除冗余的 Windows 原生顶部标题栏，保留任务栏洛雪图标、圆角阴影与四边原生拖拽缩放。"""
        if getattr(self, '_hidden', False) or sys.platform != 'win32':
            return
        try:
            import ctypes
            self.root.update_idletasks()
            u32 = ctypes.windll.user32
            hwnd = u32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            self._hwnd = hwnd
            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            style = u32.GetWindowLongW(hwnd, GWL_STYLE)
            if style & WS_CAPTION:
                u32.SetWindowLongW(hwnd, GWL_STYLE, style & ~WS_CAPTION)
                u32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
            self._sync_dwm_border_color()
            _apply_win32_hwnd_icon(hwnd)
        except Exception:
            pass

    def _sync_dwm_border_color(self):
        if getattr(self, '_hidden', False) or sys.platform != 'win32':
            return
        try:
            import ctypes
            u32 = ctypes.windll.user32
            dwm = ctypes.windll.dwmapi
            hwnd = self._hwnd or u32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            r, g, b = hex_rgb(self.C.get('bg', '#f5f2eb'))
            colorref = ctypes.c_uint32((b << 16) | (g << 8) | r)
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), 4)
            dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(colorref), 4)
        except Exception:
            pass

    def _start_win_drag(self, event=None):
        """记录鼠标按下时相对窗口左上角的偏移量（兼容移除 WS_CAPTION 后的无标题栏窗口）。"""
        self._close_popover()
        if event is None:
            return
        try:
            if sys.platform == 'win32':
                import ctypes
                import ctypes.wintypes as wt
                u32 = ctypes.windll.user32
                hwnd = self._hwnd or u32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                rc = wt.RECT()
                u32.GetWindowRect(hwnd, ctypes.byref(rc))
                self._drag_offset = (event.x_root - rc.left, event.y_root - rc.top)
            else:
                self._drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())
        except Exception:
            self._drag_offset = None

    def _on_win_drag(self, event=None):
        """按住顶栏拖动鼠标时，通过 Win32 SetWindowPos (SWP_NOSIZE) 零开销移动窗口；若处于最大化则自动还原跟随。"""
        if event is None or self._drag_offset is None:
            return
        try:
            dx, dy = self._drag_offset
            if getattr(self, '_is_maximized', False):
                self._is_maximized = False
                if hasattr(self, '_max_btn') and self._max_btn.winfo_exists():
                    self._max_btn.configure(text='□')
                w, h = _initial_size(self.ui_scale)
                if self._normal_geom and 'x' in self._normal_geom:
                    try:
                        wh_part = self._normal_geom.split('+')[0]
                        w, h = [int(v) for v in wh_part.split('x')[:2]]
                    except Exception:
                        pass
                dx = int(w * 0.45)
                dy = max(14, min(dy, 36))
                self._drag_offset = (dx, dy)
                nx = event.x_root - dx
                ny = max(0, event.y_root - dy)
                self.root.geometry('{}x{}+{}+{}'.format(w, h, nx, ny))
                return
            nx = int(event.x_root - dx)
            ny = int(event.y_root - dy)
            if sys.platform == 'win32':
                import ctypes
                u32 = ctypes.windll.user32
                hwnd = self._hwnd or u32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                u32.SetWindowPos(hwnd, 0, nx, ny, 0, 0, 0x0015)  # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
            else:
                self.root.geometry('+{}+{}'.format(nx, ny))
        except Exception:
            pass

    def _bind_header_drag(self, widget):
        if widget is None:
            return
        try:
            widget.bind('<ButtonPress-1>', self._start_win_drag, add='+')
            widget.bind('<B1-Motion>', self._on_win_drag, add='+')
            widget.bind('<Double-Button-1>', self._win_toggle_maximize, add='+')
        except Exception:
            pass

    def _win_minimize(self):
        self._close_popover()
        try:
            if sys.platform == 'win32':
                import ctypes
                u32 = ctypes.windll.user32
                hwnd = self._hwnd or u32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                u32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                return
        except Exception:
            pass
        try:
            self.root.iconify()
        except Exception:
            pass

    def _win_toggle_maximize(self, _event=None):
        self._close_popover()
        try:
            if not getattr(self, '_is_maximized', False):
                self._normal_geom = self.root.geometry()
                if sys.platform == 'win32':
                    import ctypes
                    import ctypes.wintypes as wt
                    rc = wt.RECT()
                    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rc), 0)
                    mw, mh = rc.right - rc.left, rc.bottom - rc.top
                    self.root.geometry('{}x{}+{}+{}'.format(mw, mh, rc.left, rc.top))
                else:
                    sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48
                    self.root.geometry('{}x{}+0+0'.format(sw, sh))
                self._is_maximized = True
            else:
                self._is_maximized = False
                if self._normal_geom:
                    self.root.geometry(self._normal_geom)
                else:
                    w, h = _initial_size(self.ui_scale)
                    self.root.geometry('{}x{}+80+50'.format(w, h))
            if hasattr(self, '_max_btn') and self._max_btn.winfo_exists():
                self._max_btn.configure(text='❐' if self._is_maximized else '□')
            self.root.after(40, self._after_resize)
        except Exception:
            pass

    # ---------------- dsh-claude-style 悬浮圆角卡片菜单 (Popover) ----------------
    def _close_popover(self, _e=None):
        pop = getattr(self, '_active_popover', None)
        self._active_popover = None
        if pop is not None:
            try:
                if pop.winfo_exists():
                    pop.destroy()
            except Exception:
                pass

    def _on_root_click(self, event):
        pop = getattr(self, '_active_popover', None)
        if pop is None:
            return
        try:
            w = event.widget
            if w is not None and str(w).startswith(str(pop)):
                return
        except Exception:
            pass
        self._close_popover()

    def _show_claude_popover(self, items, anchor_widget=None, x_root=None, y_root=None, min_width=168):
        """复刻 dsh-claude-style `.dsh-claude-popover-card`：
        圆角 12px 悬浮卡片、1px 细腻边框、柔和悬停底板与赤陶橙选中对勾，彻底告别丑陋的原生 Win32 菜单。"""
        ctk, C = self.ctk, self.C
        self._close_popover()
        pop = tk.Toplevel(self.root)
        self._active_popover = pop
        pop.withdraw()
        pop.overrideredirect(True)
        try:
            pop.attributes('-topmost', True)
        except Exception:
            pass
        chroma = '#010203'
        try:
            pop.configure(bg=chroma)
            pop.attributes('-transparentcolor', chroma)
        except Exception:
            pop.configure(bg=C['card'])

        card = ctk.CTkFrame(
            pop, fg_color=C['card'], corner_radius=12,
            border_width=1, border_color=C.get('card_border', C['border']),
            bg_color=chroma if sys.platform == 'win32' else 'transparent',
        )
        card.pack(fill='both', expand=True, padx=1, pady=1)
        inner = ctk.CTkFrame(card, fg_color='transparent')
        inner.pack(fill='both', expand=True, padx=6, pady=6)

        row_h = max(30, int(30 * max(1.0, (self.ui_scale - 1.0) * 0.4 + 1.0)))
        char_px = max(12, int(self.font_sizes.get('small', 11) * 1.38))

        flat_rows = []
        for it in items:
            if it is None:
                flat_rows.append(None)
                continue
            lbl, act = it[0], it[1]
            if isinstance(act, (list, tuple)):
                flat_rows.append((lbl, None, True))
                for sub_lbl, sub_act in act[:8]:
                    flat_rows.append(('  · ' + str(sub_lbl), sub_act, False))
            else:
                flat_rows.append((lbl, act, False))

        max_w = int(min_width * max(1.0, (self.ui_scale - 1.0) * 0.45 + 1.0))
        for r in flat_rows:
            if r is not None:
                max_w = max(max_w, int(len(str(r[0])) * char_px + 34))
        max_w = min(max_w, 420)

        for r in flat_rows:
            if r is None:
                div = ctk.CTkFrame(inner, height=1, fg_color=C.get('divider', C['border']))
                div.pack(fill='x', padx=6, pady=4)
                continue
            raw_lbl, cb, is_header = r
            text = str(raw_lbl)
            is_active = text.startswith('✓ ')
            if is_active:
                clean_lbl = '✓  ' + text[2:].lstrip()
            elif text.startswith('    '):
                clean_lbl = '     ' + text[4:]
            else:
                clean_lbl = '  ' + text

            if is_header or cb is None:
                lbl_w = ctk.CTkLabel(
                    inner, text=clean_lbl, font=self.f_tiny if is_header else self.f_small,
                    text_color=C['muted'] if is_header else C['faint'],
                    anchor='w', width=max_w, height=max(24, row_h - 6),
                )
                lbl_w.pack(fill='x', padx=2, pady=1)
                continue

            def _invoke(fn=cb):
                self._close_popover()
                if fn:
                    self.root.after(10, fn)

            btn = ctk.CTkButton(
                inner, text=clean_lbl, command=_invoke,
                width=max_w, height=row_h, corner_radius=7, anchor='w',
                font=self.f_bold if is_active else self.f_small,
                fg_color=C.get('row_sel', C['card2']) if is_active else 'transparent',
                hover_color=C['hover'],
                text_color=C['accent'] if is_active else C['text'],
            )
            btn.pack(fill='x', padx=1, pady=1)

        pop.bind('<Escape>', self._close_popover)
        pop.bind('<FocusOut>', lambda e: self.root.after(60, self._check_popover_focus))
        try:
            pop.update_idletasks()
            pw = max(max_w + 16, pop.winfo_reqwidth())
            ph = pop.winfo_reqheight()
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            if anchor_widget is not None:
                ax = anchor_widget.winfo_rootx()
                ay = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + 4
                if ay + ph > sh - 48:
                    ay = max(12, anchor_widget.winfo_rooty() - ph - 4)
            else:
                ax = x_root if x_root is not None else self.root.winfo_pointerx()
                ay = y_root if y_root is not None else self.root.winfo_pointery()
                if ay + ph > sh - 48:
                    ay = max(12, ay - ph)
            ax = max(10, min(ax, sw - pw - 14))
            pop.geometry('{}x{}+{}+{}'.format(pw, ph, ax, ay))
            pop.deiconify()
            pop.focus_force()
        except Exception:
            pass

    def _check_popover_focus(self):
        pop = getattr(self, '_active_popover', None)
        if pop is None:
            return
        try:
            if not pop.winfo_exists():
                self._active_popover = None
                return
            focused = pop.focus_get()
            if focused is None or not str(focused).startswith(str(pop)):
                self._close_popover()
        except Exception:
            self._close_popover()

    def _popup_menu(self, event, items):
        """右键上下文菜单：统一走 dsh-claude-style 圆角悬浮卡片，不再用原生 tk.Menu。"""
        self._show_claude_popover(items, x_root=event.x_root, y_root=event.y_root, min_width=176)

    # ---------------- 构建控件辅助 ----------------
    def _menu_btn(self, master, text, items, kind='ghost', width=None):
        """dsh-claude-style 胶囊下拉按钮：点击弹出圆角悬浮菜单卡片。"""
        btn = self._btn(master, text, None, kind=kind, width=width)

        def popup(_e=None):
            self.root.after(1, lambda: self._show_claude_popover(items, anchor_widget=btn))

        btn.configure(command=popup)
        return btn

    def _select_btn(self, master, variable, values_fn, on_pick, width=116, height=None):
        """dsh-claude-style 选择器芯片（替代丑陋的 CTkOptionMenu 原生下拉）。"""
        C = self.C
        h = height or max(28, int(28 * max(1.0, (self.ui_scale - 1.0) * 0.4 + 1.0)))
        w = int(width * max(1.0, (self.ui_scale - 1.0) * 0.5 + 1.0))
        btn = self.ctk.CTkButton(
            master, text='{}  ▾'.format(variable.get()),
            width=w, height=h, corner_radius=8, font=self.f_tiny,
            fg_color=C['field'], hover_color=C['hover'], text_color=C['text'],
            border_width=1, border_color=C['border'],
        )

        def _sync_text(*_a):
            try:
                if btn.winfo_exists():
                    btn.configure(text='{}  ▾'.format(variable.get()))
            except Exception:
                pass

        variable.trace_add('write', _sync_text)

        def _open():
            cur = variable.get()
            vals = values_fn() if callable(values_fn) else list(values_fn)
            menu_items = [
                (('✓ ' if v == cur else '    ') + str(v),
                 lambda val=v: (variable.set(val), on_pick(val) if on_pick else None))
                for v in vals
            ]
            self._show_claude_popover(menu_items, anchor_widget=btn, min_width=max(140, w))

        btn.configure(command=lambda: self.root.after(1, _open))
        return btn

    def _btn(self, master, text, command, kind='ghost', width=None, height=None):
        char_px = max(13, int(self.font_sizes.get('btn', 11) * 1.42))
        auto_w = int(len(text) * char_px + 22)
        w = max(int((width or 76) * max(1.0, (self.ui_scale - 1.0) * 0.52 + 1.0)), auto_w)
        h = height or max(30, int(30 * max(1.0, (self.ui_scale - 1.0) * 0.42 + 1.0)))
        cfg = dict(width=w, height=h, corner_radius=8, font=self.f_btn, command=command, text=text)
        if kind == 'primary':
            cfg.update(fg_color=self.C['accent'], hover_color=self.C['accent_hover'],
                       text_color=PALETTE['on_accent'], font=self.f_bold)
        elif kind == 'danger':
            cfg.update(fg_color=self.C.get('danger_bg', '#fbeae8'), hover_color=self.C['danger'],
                       text_color=self.C['danger'], border_width=1, border_color=self.C['danger'])
        elif kind == 'subtle':
            cfg.update(fg_color=self.C['field'], hover_color=self.C['hover'], text_color=self.C['text'],
                       border_width=1, border_color=self.C['border'])
        else:
            cfg.update(fg_color=self.C['card'], hover_color=self.C['hover'], text_color=self.C['text'],
                       border_width=1, border_color=self.C['border'])
        return self.ctk.CTkButton(master, **cfg)

    def _build(self):
        ctk, C = self.ctk, self.C
        try:
            win_w = self.root.winfo_width()
            if win_w <= 200:
                win_w, _ = _initial_size(self.ui_scale)
            if getattr(self, '_is_maximized', False):
                win_w = max(win_w, _screen_size()[0])
        except Exception:
            win_w = 1340
        eff_scale = self.ui_scale * _viewport_font_boost(win_w)
        self._effective_scale = eff_scale
        sz = _scale_fonts(eff_scale, FONT_BASE)
        self.font_sizes = sz
        self.f_title = ctk.CTkFont(family=FONT_SERIF, size=sz['title'], weight='bold')
        self.f_card = ctk.CTkFont(family=FONT_SERIF, size=sz['card'], weight='bold')
        self.f_base = ctk.CTkFont(family=FONT_FAMILY, size=sz['base'])
        self.f_bold = ctk.CTkFont(family=FONT_SANS_BOLD, size=sz['bold'], weight='bold')
        self.f_small = ctk.CTkFont(family=FONT_FAMILY, size=sz['small'])
        self.f_tiny = ctk.CTkFont(family=FONT_FAMILY, size=sz['tiny'])
        self.f_btn = ctk.CTkFont(family=FONT_FAMILY, size=sz['btn'])
        self.f_mono = ctk.CTkFont(family=FONT_MONO, size=sz['tiny'])
        self.f_log = ctk.CTkFont(family=FONT_MONO, size=sz['log'])
        cur_theme_key = self.settings.get('theme') or 'green'
        self._icon_small = _make_icon(zoom=1, theme=cur_theme_key)
        chk_sz = int(16 * max(1.0, (eff_scale - 1.0) * 0.4 + 1.0))
        self._chk_imgs = _get_checkbox_images(chk_sz, C)

        self.root.grid_rowconfigure(1, weight=5)
        self.root.grid_columnconfigure(0, weight=1)

        # ---------- 一体化无边框顶栏（随主题切换图标 + 可拖拽标题区 + 右侧窗口控制按钮） ----------
        header = ctk.CTkFrame(self.root, fg_color=C['card'], corner_radius=12,
                              border_width=1, border_color=C.get('card_border', C['border']))
        _throttle_ctk_frame_redraw(header)
        header.grid(row=0, column=0, sticky='ew', padx=14, pady=(8, 4))

        left_hdr = tk.Frame(header, bg=C['card'])
        left_hdr.pack(side='left', fill='y', padx=(14, 8), pady=7)
        self._icon_lbl = tk.Label(left_hdr, image=self._icon_small, bg=C['card'], borderwidth=0, cursor='fleur')
        self._icon_lbl.pack(side='left', padx=(0, 10))
        self._title_lbl = tk.Label(left_hdr, text='LX Music 音源管理工具', font=self.f_title,
                                   bg=C['card'], fg=C['text'], cursor='fleur')
        self._title_lbl.pack(side='left')
        ver_lbl = tk.Label(left_hdr, text=' v{} '.format(__version__), bg=C['card2'], fg=C['accent'],
                           font=self.f_mono, padx=5, pady=1, cursor='fleur')
        ver_lbl.pack(side='left', padx=(8, 0))

        # 绑定顶栏空白（含 CTkFrame 内部 _canvas）与标题拖拽移动窗口、双击最大化/还原
        for drag_w in (header, getattr(header, '_canvas', None), left_hdr, self._icon_lbl, self._title_lbl, ver_lbl):
            self._bind_header_drag(drag_w)

        # 右侧窗口控制区 [─] [□] [✕] + 工具栏按钮（使用原生 tk.Frame 消除缩放时透明 CTkFrame 重绘开销）
        win_ctrls = tk.Frame(header, bg=C['card'])
        win_ctrls.pack(side='right', padx=(4, 10), pady=7)
        ctrl_h = max(28, int(28 * max(1.0, (self.ui_scale - 1.0) * 0.35 + 1.0)))
        ctrl_w = max(32, int(32 * max(1.0, (self.ui_scale - 1.0) * 0.35 + 1.0)))
        ctk.CTkButton(
            win_ctrls, text='─', width=ctrl_w, height=ctrl_h, corner_radius=7,
            fg_color=C['card'], hover_color=C['hover'], text_color=C['muted'],
            font=self.f_bold, command=self._win_minimize,
        ).pack(side='left', padx=1)
        self._max_btn = ctk.CTkButton(
            win_ctrls, text='❐' if getattr(self, '_is_maximized', False) else '□',
            width=ctrl_w, height=ctrl_h, corner_radius=7,
            fg_color=C['card'], hover_color=C['hover'], text_color=C['muted'],
            font=self.f_bold, command=self._win_toggle_maximize,
        )
        self._max_btn.pack(side='left', padx=1)
        ctk.CTkButton(
            win_ctrls, text='✕', width=ctrl_w, height=ctrl_h, corner_radius=7,
            fg_color=C['card'], hover_color=C['danger'], text_color=C['muted'],
            font=self.f_bold, command=self.on_close,
        ).pack(side='left', padx=(1, 0))

        tk.Frame(header, bg=C['divider'], width=1, height=22).pack(side='right', padx=(4, 4), pady=10)

        btns = tk.Frame(header, bg=C['card'])
        btns.pack(side='right', padx=(4, 4), pady=7)

        cur_theme_lbl = THEMES.get(cur_theme_key, THEMES['green'])['label'].split('（')[0].split(' ')[0]
        theme_items = [
            (('✓ ' if k == cur_theme_key else '    ') + THEMES[k]['label'],
             lambda key=k: self.do_set_theme(key))
            for k in THEME_ORDER
        ]
        self._menu_btn(btns, '主题 · {} ▾'.format(cur_theme_lbl), theme_items, kind='subtle', width=92).pack(
            side='left', padx=(0, 5))

        cur_scale_pct = int(round(float(self.settings.get('ui_scale') or 1.0) * 100))
        scale_presets = [
            (90, '紧凑 90%'),
            (100, '标准 100%'),
            (115, '适中 115%'),
            (130, '大号 130%'),
            (150, '特大 150%'),
            (175, '超大 175%'),
            (200, '巨字 200%'),
        ]
        scale_items = [
            (('✓ ' if abs(cur_scale_pct - p) <= 4 else '    ') + lbl,
             lambda val=p / 100.0: self.do_set_ui_scale(val))
            for p, lbl in scale_presets
        ]
        self._menu_btn(btns, '字号 {}% ▾'.format(cur_scale_pct), scale_items, kind='subtle', width=86).pack(
            side='left', padx=(0, 5))

        self.btn_restart = self._btn(btns, '重启洛雪', self.do_restart_lx_music, kind='primary', width=82)
        self.btn_restart.pack(side='left', padx=(0, 5))
        self._btn(btns, '偏好设置', self.do_open_settings, width=78).pack(side='left', padx=(0, 5))
        self._menu_btn(btns, '更多 ▾', [
            ('★ 官方精选音源库…', self.do_add_recommended),
            ('检查工具自身更新', self.do_check_app_update),
            None,
            ('重新定位 user_api.json…', self.do_relocate),
            ('打开洛雪数据目录', self.do_open_data_dir),
            ('打开自动备份目录', self.do_open_backup_dir),
        ], width=68).pack(side='left')

        # ---------- 主区（外层布局容器改用原生 tk.Frame，零 Canvas 重绘开销） ----------
        main = tk.Frame(self.root, bg=C['bg'])
        main.grid(row=1, column=0, sticky='nsew', padx=14, pady=4)
        main.grid_columnconfigure((0, 1), weight=1, uniform='col')
        main.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(main, fg_color=C['card'], corner_radius=12,
                            border_width=1, border_color=C.get('card_border', C['border']))
        _throttle_ctk_frame_redraw(left)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        right = ctk.CTkFrame(main, fg_color=C['card'], corner_radius=12,
                             border_width=1, border_color=C.get('card_border', C['border']))
        _throttle_ctk_frame_redraw(right)
        right.grid(row=0, column=1, sticky='nsew', padx=(6, 0))
        self._build_left_card(left)
        self._build_right_card(right)

        # ---------- 底部（备份 + 订阅 + 日志，移除 uniform 强行压缩，小屏自适应不遮挡） ----------
        bottom = tk.Frame(self.root, bg=C['bg'])
        bottom.grid(row=2, column=0, sticky='nsew', padx=14, pady=(4, 4))
        bottom.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=2, minsize=int(215 * max(1.0, (self.ui_scale - 1.0) * 0.4 + 1.0)))
        bottom.grid_columnconfigure(0, weight=3, minsize=250)
        bottom.grid_columnconfigure(1, weight=5, minsize=380)
        bottom.grid_columnconfigure(2, weight=4, minsize=280)
        self._bottom = bottom
        self._build_bottom(bottom)

        # ---------- 状态栏（左侧状态提示 + 右侧数据路径 + 下载进度条） ----------
        status = tk.Frame(self.root, bg=C['bg'])
        status.grid(row=3, column=0, sticky='ew', padx=16, pady=(0, 6))
        status.grid_columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value=self.STATUS_HINT)
        self.status_label = ctk.CTkLabel(status, textvariable=self.status_var, font=self.f_tiny,
                                         text_color=C['faint'], anchor='w')
        self.status_label.grid(row=0, column=0, sticky='ew')
        self.path_label = ctk.CTkLabel(status, text='', font=self.f_mono, text_color=C['faint'], anchor='e')
        self.path_label.grid(row=0, column=1, sticky='e', padx=(12, 0))
        self.hint_label = self.status_label
        self.prog_row = tk.Frame(self.root, bg=C['bg'])
        self.prog_row.grid(row=4, column=0, sticky='ew', padx=16, pady=(0, 8))
        self.prog_row.grid_columnconfigure(0, weight=1)
        self.prog_bar = ctk.CTkProgressBar(self.prog_row, height=7, corner_radius=4,
                                           fg_color=C['field'], progress_color=C['accent'])
        self.prog_bar.set(0)
        self.prog_bar.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        self.prog_text = ctk.CTkLabel(self.prog_row, text='', font=self.f_mono, text_color=C['accent'])
        self.prog_text.grid(row=0, column=1, sticky='e')
        self.prog_row.grid_remove()

    def _on_search_typed(self, _evt=None):
        text = self.search_entry.get() or ''
        if text == BaseApp.SEARCH_HINT:
            text = ''
        if (self.search_var.get() or '') != text:
            self.search_var.set(text)
            self._on_search()

    def _clear_search(self):
        try:
            self.search_entry.delete(0, 'end')
            self.search_var.set('')
            self._on_search()
            self.root.focus_set()
        except Exception:
            pass

    def _switch_import_mode(self, mode_label):
        """dsh-claude-style 胶囊拨杆切换导入模式（仅新增 / 同名更新）。"""
        self.mode_var.set(mode_label)
        self._set_mode(mode_label)
        self._sync_mode_pills()

    def _sync_mode_pills(self):
        C = self.C
        is_upd = (self.import_mode == 'update')
        try:
            if hasattr(self, '_pill_add') and self._pill_add.winfo_exists():
                self._pill_add.configure(
                    fg_color=C['card2'] if not is_upd else 'transparent',
                    hover_color=C['card2'] if not is_upd else C['hover'],
                    text_color=C['accent'] if not is_upd else C['muted'],
                )
            if hasattr(self, '_pill_upd') and self._pill_upd.winfo_exists():
                self._pill_upd.configure(
                    fg_color=C['card2'] if is_upd else 'transparent',
                    hover_color=C['card2'] if is_upd else C['hover'],
                    text_color=C['accent'] if is_upd else C['muted'],
                )
        except Exception:
            pass

    def _build_left_card(self, card):
        ctk, C = self.ctk, self.C
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)

        # 标题优先 side='left' 占位，彻底杜绝小屏下副标题覆盖主标题
        head = tk.Frame(card, bg=C['card'])
        head.grid(row=0, column=0, sticky='ew', padx=14, pady=(10, 3))
        ctk.CTkLabel(head, text='待导入音源', font=self.f_card, text_color=C['text']).pack(side='left', padx=(0, 8))
        self.folder_label = ctk.CTkLabel(head, text='可从「精选源库」、本地文件夹或下方订阅加载',
                                         font=self.f_tiny, text_color=C['faint'], anchor='e')
        self.folder_label.pack(side='right')

        bar = tk.Frame(card, bg=C['card'])
        bar.grid(row=1, column=0, sticky='ew', padx=14, pady=(2, 4))
        self._btn(bar, '选择文件夹', self.do_scan_folder, kind='primary', width=92).pack(side='left', padx=(0, 4))
        self._btn(bar, '★ 精选源库', self.do_add_recommended, kind='subtle', width=88).pack(side='left', padx=2)
        self._btn(bar, '智能勾选', self.do_smart_select, width=70).pack(side='left', padx=2)
        self._btn(bar, '全选', lambda: self.do_select_all_candidates(True), width=48).pack(side='left', padx=2)
        self._btn(bar, '全不选', lambda: self.do_select_all_candidates(False), width=56).pack(side='left', padx=2)
        self._menu_btn(bar, '清理 ▾', [
            ('移除所选候选音源', self.do_remove_candidates),
            ('清空全部待导入列表', self.do_clear_candidates),
        ], width=60).pack(side='left', padx=2)

        self.search_var = tk.StringVar()
        s_frame = ctk.CTkFrame(card, fg_color=C['field'], corner_radius=8,
                               border_width=1, border_color=C['border'], height=32)
        _throttle_ctk_frame_redraw(s_frame)
        s_frame.grid(row=2, column=0, sticky='ew', padx=14, pady=(2, 4))
        s_frame.grid_propagate(False)
        s_frame.grid_columnconfigure(1, weight=1)
        tk.Label(s_frame, text='⌕', bg=C['field'], fg=C['muted'], font=self.f_base).grid(
            row=0, column=0, padx=(10, 4), pady=4)
        self.search_entry = tk.Entry(s_frame, bg=C['field'], fg=C['text'], insertbackground=C['text'],
                                     relief='flat', borderwidth=0, highlightthickness=0, font=self.f_small)
        self.search_entry.grid(row=0, column=1, sticky='ew', pady=5)
        self._setup_placeholder(self.search_entry, BaseApp.SEARCH_HINT)
        self.search_entry.bind('<KeyRelease>', self._on_search_typed)
        self.search_entry.bind('<Return>', self._on_search_typed)
        clr_lbl = tk.Label(s_frame, text='✕', bg=C['field'], fg=C['faint'], font=self.f_tiny, cursor='hand2')
        clr_lbl.grid(row=0, column=2, padx=(4, 10), pady=4)
        clr_lbl.bind('<Button-1>', lambda e: self._clear_search())

        _cand_holder = tk.Frame(card, bg=C['card'])
        _cand_holder.grid_propagate(False)
        _cand_holder.grid(row=3, column=0, sticky='nsew', padx=10, pady=2)
        self.cand_list = self.SmoothFrame(_cand_holder, fg_color=C['card'], corner_radius=0,
                                          scrollbar_button_color=C['border'], scrollbar_button_hover_color=C['faint'])
        self.cand_list.pack(fill='both', expand=True)
        try:
            self.cand_list._parent_canvas.configure(bg=C['card'], highlightthickness=0)
        except Exception:
            pass
        self.cand_rows = {}
        self.cand_checks = {}

        # dsh-claude-style 一体式底栏：左侧内凹胶囊模式开关 [仅新增 | 同名更新] + 主操作按钮 + 右侧计数
        act = tk.Frame(card, bg=C['card'])
        act.grid(row=4, column=0, sticky='ew', padx=14, pady=(6, 2))
        cur_mode_lbl = MODE_UPDATE_LABEL if getattr(self, 'import_mode', 'add') == 'update' else MODE_ADD_LABEL
        self.mode_var = tk.StringVar(value=cur_mode_lbl)
        pill_h = max(26, int(26 * max(1.0, (self.ui_scale - 1.0) * 0.4 + 1.0)))
        mode_track = ctk.CTkFrame(act, fg_color=C['field'], corner_radius=8,
                                  border_width=1, border_color=C['border'])
        mode_track.pack(side='left', padx=(0, 6))
        self._pill_add = ctk.CTkButton(
            mode_track, text=MODE_ADD_LABEL, width=64, height=pill_h, corner_radius=6,
            fg_color=C['card2'], hover_color=C['card2'], text_color=C['accent'], font=self.f_bold,
            cursor='hand2',
            command=lambda: self._switch_import_mode(MODE_ADD_LABEL),
        )
        self._pill_add.pack(side='left', padx=(2, 1), pady=2)
        self._pill_upd = ctk.CTkButton(
            mode_track, text=MODE_UPDATE_LABEL, width=76, height=pill_h, corner_radius=6,
            fg_color='transparent', hover_color=C['hover'], text_color=C['muted'], font=self.f_bold,
            cursor='hand2',
            command=lambda: self._switch_import_mode(MODE_UPDATE_LABEL),
        )
        self._pill_upd.pack(side='left', padx=(1, 2), pady=2)
        self._sync_mode_pills()

        self.btn_import_sel = self._btn(act, '导入所选', self.do_import, kind='primary', width=96)
        self.btn_import_sel.pack(side='left', padx=(0, 5))
        self.btn_import_all = self._btn(act, '一键全部导入', lambda: self.do_import(all_selected=True),
                                        kind='subtle', width=98)
        self.btn_import_all.pack(side='left')
        self.cand_count = ctk.CTkLabel(act, text='', font=self.f_mono, text_color=C['muted'])
        self.cand_count.pack(side='right')

        self.cand_hint = ctk.CTkLabel(
            card, text='提示：「智能勾选」自动选中新源与可升级项；点下方订阅的「拉取挑选」可把仓库音源载入此处自由勾选',
            font=self.f_tiny, text_color=C['faint'], anchor='w')
        self.cand_hint.grid(row=5, column=0, sticky='w', padx=14, pady=(2, 8))

    def _build_right_card(self, card):
        ctk, C = self.ctk, self.C
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        head = tk.Frame(card, bg=C['card'])
        head.grid(row=0, column=0, sticky='ew', padx=14, pady=(10, 3))
        ctk.CTkLabel(head, text='已导入音源', font=self.f_card, text_color=C['text']).pack(side='left', padx=(0, 8))
        self._btn(head, '刷新', self._view_refresh_imported, width=58).pack(side='right')
        self.imp_count = ctk.CTkLabel(head, text='', font=self.f_mono, text_color=C['muted'])
        self.imp_count.pack(side='right', padx=(0, 8))

        _imp_holder = tk.Frame(card, bg=C['card'])
        _imp_holder.grid_propagate(False)
        _imp_holder.grid(row=2, column=0, sticky='nsew', padx=10, pady=2)
        self.imp_list = self.SmoothFrame(_imp_holder, fg_color=C['card'], corner_radius=0,
                                         scrollbar_button_color=C['border'], scrollbar_button_hover_color=C['faint'])
        self.imp_list.pack(fill='both', expand=True)
        try:
            self.imp_list._parent_canvas.configure(bg=C['card'], highlightthickness=0)
        except Exception:
            pass
        self.imp_rows = {}
        self.imp_checks = {}

        act = tk.Frame(card, bg=C['card'])
        act.grid(row=3, column=0, sticky='ew', padx=14, pady=(6, 2))
        self._btn(act, '删除所选', self.do_delete_imported, width=84).pack(side='left', padx=(0, 5))
        self._btn(act, '一键清除全部', self.do_clear_imported, kind='danger', width=104).pack(side='left', padx=(0, 6))
        self._btn(act, '全选', lambda: self._imp_select_all(True), kind='subtle', width=50).pack(side='left', padx=(0, 4))
        self._btn(act, '取消全选', lambda: self._imp_select_all(False), kind='subtle', width=66).pack(side='left')

        ctk.CTkLabel(card, text='提示：双击音源可查看脚本源码与详情；修改 user_api.json 后点顶栏「重启洛雪」立即生效',
                     font=self.f_tiny, text_color=C['faint'], anchor='w').grid(
            row=4, column=0, sticky='w', padx=14, pady=(2, 8))

    def _imp_select_all(self, select=True):
        self.checked_imported = set(range(len(self.entries))) if select else set()
        for i in range(len(self.entries)):
            self._imp_sync(i)

    def _build_bottom(self, bottom):
        ctk, C = self.ctk, self.C
        bdr = C.get('card_border', C['border'])

        # ---- 1. 备份文件（标题优先 side='left' 占位，按钮紧凑化，小屏绝不覆盖标题） ----
        bk = ctk.CTkFrame(bottom, fg_color=C['card'], corner_radius=12, border_width=1, border_color=bdr)
        _throttle_ctk_frame_redraw(bk)
        bk.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        self._bk_card = bk
        bk.grid_columnconfigure(0, weight=1)
        bk.grid_rowconfigure(1, weight=1)
        bk_head = tk.Frame(bk, bg=C['card'])
        bk_head.grid(row=0, column=0, sticky='ew', padx=12, pady=(8, 3))
        ctk.CTkLabel(bk_head, text='备份文件', font=self.f_card, text_color=C['text'], anchor='w').pack(
            side='left', padx=(0, 6))
        bk_btns = tk.Frame(bk_head, bg=C['card'])
        bk_btns.pack(side='right')
        self._btn(bk_btns, '备份', self.do_backup, width=48).pack(side='left', padx=2)
        self._btn(bk_btns, '还原', self.do_restore_backup, kind='primary', width=48).pack(side='left', padx=2)
        self._menu_btn(bk_btns, '▾', [
            ('打开备份文件夹', self.do_open_backup_dir),
            None,
            ('删除所选备份', self.do_delete_backups),
            ('清空全部备份', self.do_clear_backups),
        ], width=30).pack(side='left', padx=(2, 0))
        _bk_holder = tk.Frame(bk, bg=C['card'], height=int(136 * self.ui_scale))
        _bk_holder.grid_propagate(False)
        _bk_holder.grid(row=1, column=0, sticky='nsew', padx=10, pady=(2, 8))
        self.bk_list = self.SmoothFrame(_bk_holder, fg_color=C['card'], corner_radius=0,
                                        scrollbar_button_color=C['border'], scrollbar_button_hover_color=C['faint'])
        self.bk_list.pack(fill='both', expand=True)
        try:
            self.bk_list._parent_canvas.configure(bg=C['card'], highlightthickness=0)
        except Exception:
            pass
        self.bk_rows = {}

        # ---- 2. 订阅更新（顶栏仅放添加/精选源库，检查/拉取/更新下沉至底栏，小屏彻底不拥挤） ----
        sub = ctk.CTkFrame(bottom, fg_color=C['card'], corner_radius=12, border_width=1, border_color=bdr)
        _throttle_ctk_frame_redraw(sub)
        sub.grid(row=0, column=1, sticky='nsew', padx=(5, 5))
        self._sub_card = sub
        sub.grid_columnconfigure(0, weight=1)
        sub.grid_rowconfigure(1, weight=1)
        sub_head = tk.Frame(sub, bg=C['card'])
        sub_head.grid(row=0, column=0, sticky='ew', padx=12, pady=(8, 3))
        ctk.CTkLabel(sub_head, text='订阅更新', font=self.f_card, text_color=C['text'], anchor='w').pack(
            side='left', padx=(0, 6))
        sub_btns = tk.Frame(sub_head, bg=C['card'])
        sub_btns.pack(side='right')
        self._btn(sub_btns, '★ 精选源库', self.do_add_recommended, kind='primary', width=84).pack(side='left', padx=2)
        self._btn(sub_btns, '＋ 添加', self.do_add_subscription, width=56).pack(side='left', padx=2)
        self._menu_btn(sub_btns, '选择 ▾', [
            ('📥 拉取所选订阅到左侧「待导入」自由挑选', lambda: self.do_fetch_sub_to_candidates(None)),
            ('🔍 检查全部订阅是否有新版本（不下载）', self.do_check_subscriptions),
            None,
            ('全选订阅', lambda: self.do_select_all_subs(True)),
            ('全不选订阅', lambda: self.do_select_all_subs(False)),
            ('只勾「有新版」的订阅', self.do_select_subs_with_update),
            ('勾选全部「已最新」的订阅', lambda: self._select_subs_by_state('latest')),
        ], width=56).pack(side='left', padx=(2, 0))

        _sub_holder = tk.Frame(sub, bg=C['card'], height=int(106 * self.ui_scale))
        _sub_holder.grid_propagate(False)
        _sub_holder.grid(row=1, column=0, sticky='nsew', padx=10, pady=(2, 2))
        self.sub_list = self.SmoothFrame(_sub_holder, fg_color=C['card'], corner_radius=0,
                                         scrollbar_button_color=C['border'], scrollbar_button_hover_color=C['faint'])
        self.sub_list.pack(fill='both', expand=True)
        try:
            self.sub_list._parent_canvas.configure(bg=C['card'], highlightthickness=0)
        except Exception:
            pass
        self.sub_rows = {}

        # 底部操作与镜像栏：左侧镜像/下载器芯片，右侧 检查 / 拉取挑选 / 一键更新
        setrow = tk.Frame(sub, bg=C['card'])
        setrow.grid(row=2, column=0, sticky='ew', padx=12, pady=(2, 8))
        cur_m = (self.settings.get('mirror') or '').strip()
        m_presets = ['ghproxy.net', 'gh.llkk.cc', 'gh-proxy.org', 'ghfast.top', '直连 (官方)', '自定义镜像…']
        cur_m_disp = '直连 (官方)' if not cur_m else cur_m.replace('https://', '').replace('http://', '').strip('/')
        if cur_m_disp not in m_presets:
            m_presets.insert(0, cur_m_disp)
        self.mirror_var = tk.StringVar(value=cur_m_disp)
        self.mirror_combo = self._select_btn(setrow, self.mirror_var, m_presets, self._on_mirror_preset, width=102)
        self.mirror_combo.pack(side='left', padx=(0, 4))
        self.dl_var = tk.StringVar(value=self.DL_LABELS.get(self.settings.get('downloader', 'auto'), '自动'))
        self.dl_menu = self._select_btn(setrow, self.dl_var, list(self.DL_LABELS.values()),
                                        self._on_downloader_pick, width=68)
        self.dl_menu.pack(side='left', padx=(0, 4))

        self.btn_sub_update = self._btn(setrow, '一键更新', self.do_update_all_subscriptions, kind='primary', width=68)
        self.btn_sub_update.pack(side='right', padx=(2, 0))
        self._btn(setrow, '拉取挑选', lambda: self.do_fetch_sub_to_candidates(None), kind='subtle', width=68).pack(
            side='right', padx=2)
        self._btn(setrow, '检查', self.do_check_subscriptions, width=46).pack(side='right', padx=2)

        # ---- 3. 运行日志 ----
        lg = ctk.CTkFrame(bottom, fg_color=C['card'], corner_radius=12, border_width=1, border_color=bdr)
        _throttle_ctk_frame_redraw(lg)
        lg.grid(row=0, column=2, sticky='nsew', padx=(5, 0))
        self._lg_card = lg
        lg.grid_columnconfigure(0, weight=1)
        lg.grid_rowconfigure(1, weight=1)
        lghead = tk.Frame(lg, bg=C['card'])
        lghead.grid(row=0, column=0, sticky='ew', padx=12, pady=(8, 3))
        ctk.CTkLabel(lghead, text='运行日志', font=self.f_card, text_color=C['text'], anchor='w').pack(
            side='left', padx=(0, 6))
        self._btn(lghead, '清空', self.do_clear_log, width=52).pack(side='right')
        _lg_holder = tk.Frame(lg, bg=C['field'], height=int(136 * self.ui_scale))
        _lg_holder.grid_propagate(False)
        _lg_holder.grid(row=1, column=0, sticky='nsew', padx=10, pady=(2, 10))
        self.logbox = ctk.CTkTextbox(_lg_holder, fg_color=C['field'], corner_radius=8,
                                     border_width=1, border_color=C['border'], font=self.f_log,
                                     wrap='char', state='disabled')
        self.logbox.pack(fill='both', expand=True)
        for tag, color in LOG_COLORS.items():
            self.logbox.tag_config(tag, foreground=color)

    # ---------------- 动画与行染色 ----------------
    def _set_row_color(self, widget, color):
        """立即设置行背景并同步非胶囊子组件（跳过带 _keep_bg 标记的胶囊标签，保持 dsh-claude-style 胶囊底色）。"""
        try:
            if getattr(widget, '_cur_bg', None) == color:
                return
            widget._cur_bg = color
            attr = 'fg_color' if 'fg_color' in widget.keys() else 'bg'
            widget.configure(**{attr: color})
            if attr == 'bg':
                for child in widget.winfo_children():
                    if getattr(child, '_keep_bg', False):
                        continue
                    try:
                        child.configure(bg=color)
                        if 'activebackground' in child.keys():
                            child.configure(activebackground=color)
                        for sub_c in child.winfo_children():
                            if not getattr(sub_c, '_keep_bg', False):
                                sub_c.configure(bg=color)
                    except Exception:
                        pass
        except Exception:
            pass

    def _make_fast_check(self, row, is_checked, on_toggle):
        """使用预渲染抗锯齿贴图的极速复选框 Label（比每行建一个 tk.Canvas 快 10 倍）。"""
        imgs = getattr(self, '_chk_imgs', None)
        if imgs is not None:
            lbl = tk.Label(row, image=imgs['on' if is_checked else 'off'],
                           bg=row.cget('bg'), bd=0, highlightthickness=0, cursor='hand2')
            lbl._is_fast_chk = True
            lbl.bind('<Button-1>', lambda e: on_toggle())
            return lbl
        chk = WebCheck(row, variable=tk.BooleanVar(value=is_checked),
                       size=int(16 * max(1.0, (self.ui_scale - 1.0) * 0.4 + 1.0)),
                       command=on_toggle)
        return chk

    def _sync_fast_check(self, chk, is_checked):
        if chk is None:
            return
        imgs = getattr(self, '_chk_imgs', None)
        if getattr(chk, '_is_fast_chk', False) and imgs is not None:
            chk.configure(image=imgs['on' if is_checked else 'off'])
        elif hasattr(chk, 'var') and bool(chk.var.get()) != is_checked:
            chk.var.set(is_checked)
            chk._draw()

    # ---------------- 候选行（dsh-claude-style 过程行风格） ----------------
    def _build_candidate_row(self, i):
        C = self.C
        s = self.candidates[i]
        sel_bg = C.get('row_sel', C['card2'])
        row_bg = sel_bg if i in self.checked_candidates else C['card']
        row = tk.Frame(self.cand_list, bg=row_bg, cursor='hand2')
        row._cur_bg = row_bg
        row.pack(fill='x', padx=6, pady=1)
        mark, mark_color, _mark_tip, _imp = self._cand_state(i)
        badge_style = {
            '新': (' ★ 新源 ', C['card2'], C['accent']),
            '↑': (' ↑ 升级 ', C.get('green_bg', C['field']), C[mark_color]),
            '=': (' = 同版 ', C['field'], C['faint']),
            '↓': (' ↓ 旧版 ', C['field'], C['faint']),
        }
        badge_txt, badge_bg, badge_fg = badge_style.get(mark, (mark, C['field'], C[mark_color]))
        chk = self._make_fast_check(row, i in self.checked_candidates, lambda idx=i: self._cand_toggle(idx))
        chk.pack(side='left', padx=(8, 6), pady=6)
        badge = tk.Label(row, text=badge_txt, bg=badge_bg, fg=badge_fg, font=self.f_tiny,
                         padx=4, pady=1, cursor='hand2')
        badge._keep_bg = True
        badge.pack(side='left', padx=(0, 6), pady=5)
        meta = tk.Label(row, text=self._cand_meta_text(s), bg=row_bg, fg=C['muted'], font=self.f_mono,
                        anchor='e', cursor='hand2')
        meta.pack(side='right', padx=(8, 10), pady=5)
        name = tk.Label(row, text=short(s.name, 26), bg=row_bg, fg=C['text'], font=self.f_bold,
                        anchor='w', cursor='hand2')
        name.pack(side='left', padx=(2, 8), pady=5)
        self.cand_rows[i] = row
        self.cand_checks[i] = chk
        row.bind('<Enter>', lambda e, idx=i, frm=row: self._row_enter(frm, idx))
        row.bind('<Leave>', lambda e, idx=i, frm=row: self._row_leave(frm, idx))
        for w in (row, badge, name, meta):
            w.bind('<Button-1>', lambda e, idx=i: self._cand_toggle(idx))
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
        self._sync_fast_check(self.cand_checks.get(i), v)
        row = self.cand_rows.get(i)
        if row is not None:
            sel_bg = self.C.get('row_sel', self.C['card2'])
            self._set_row_color(row, sel_bg if v else self.C['card'])
        self._update_action_buttons()
        self._refresh_count_label()

    def _row_enter(self, row, i):
        prev = getattr(self, '_hovered_cand', None)
        if prev is not None and prev[1] != i:
            p_row, p_idx = prev
            sel_bg = self.C.get('row_sel', self.C['card2'])
            self._set_row_color(p_row, sel_bg if p_idx in self.checked_candidates else self.C['card'])
        self._hovered_cand = (row, i)
        if i not in self.checked_candidates:
            self._set_row_color(row, self.C['hover'])

    def _row_leave(self, row, i):
        sel_bg = self.C.get('row_sel', self.C['card2'])
        self._set_row_color(row, sel_bg if i in self.checked_candidates else self.C['card'])

    def _refresh_count_label(self):
        shown = sum(1 for i in range(len(self.candidates)) if self._candidate_visible(i))
        total = len(self.candidates)
        self.cand_count.configure(text='共 {} 个{} · 已选 {}'.format(
            total, (' · 显示 {}'.format(shown) if shown != total else ''), len(self.checked_candidates)))

    # ---------------- 已导入行 ----------------
    def _build_imported_row(self, i, e):
        C = self.C
        sel_bg = C.get('row_sel', C['card2'])
        row_bg = sel_bg if i in self.checked_imported else C['card']
        row = tk.Frame(self.imp_list, bg=row_bg, cursor='hand2')
        row._cur_bg = row_bg
        row.pack(fill='x', padx=6, pady=1)
        chk = self._make_fast_check(row, i in self.checked_imported, lambda idx=i: self._imp_toggle(idx))
        chk.pack(side='left', padx=(8, 6), pady=6)
        ver_txt = ' v{} '.format(e.get('version') or '?')
        ver_pill = tk.Label(row, text=ver_txt, bg=C['field'], fg=C['muted'], font=self.f_mono,
                            padx=4, pady=0, cursor='hand2')
        ver_pill._keep_bg = True
        ver_pill.pack(side='right', padx=(4, 10), pady=5)
        author_txt = short(e.get('author') or '', 14)
        if author_txt:
            meta = tk.Label(row, text=author_txt, bg=row_bg, fg=C['faint'], font=self.f_tiny,
                            anchor='e', cursor='hand2')
            meta.pack(side='right', padx=(4, 2), pady=5)
        else:
            meta = None
        name = tk.Label(row, text=short(e.get('name', ''), 26), bg=row_bg, fg=C['text'], font=self.f_bold,
                        anchor='w', cursor='hand2')
        name.pack(side='left', padx=(2, 8), pady=5)
        self.imp_rows[i] = row
        self.imp_checks[i] = chk
        row.bind('<Enter>', lambda ev, idx=i, frm=row: self._imp_enter(frm, idx))
        row.bind('<Leave>', lambda ev, idx=i, frm=row: self._imp_leave(frm, idx))
        for w in ([row, name, ver_pill] + ([meta] if meta else [])):
            w.bind('<Button-1>', lambda ev, idx=i: self._imp_toggle(idx))
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
        self._sync_fast_check(self.imp_checks.get(i), v)
        row = self.imp_rows.get(i)
        if row is not None:
            sel_bg = self.C.get('row_sel', self.C['card2'])
            self._set_row_color(row, sel_bg if v else self.C['card'])
        self.imp_count.configure(text='共 {} 个 · 已选 {}'.format(len(self.entries), len(self.checked_imported)))

    def _imp_enter(self, row, i):
        prev = getattr(self, '_hovered_imp', None)
        if prev is not None and prev[1] != i:
            p_row, p_idx = prev
            sel_bg = self.C.get('row_sel', self.C['card2'])
            self._set_row_color(p_row, sel_bg if p_idx in self.checked_imported else self.C['card'])
        self._hovered_imp = (row, i)
        if i not in self.checked_imported:
            self._set_row_color(row, self.C['hover'])

    def _imp_leave(self, row, i):
        sel_bg = self.C.get('row_sel', self.C['card2'])
        self._set_row_color(row, sel_bg if i in self.checked_imported else self.C['card'])

    # ---------------- 备份行 ----------------
    def _bk_toggle(self, name, row):
        if name in self.checked_backups:
            self.checked_backups.discard(name)
        else:
            self.checked_backups.add(name)
        self._bk_sync(name, row)

    def _bk_sync(self, name, row):
        sel_bg = self.C.get('row_sel', self.C['card2'])
        self._set_row_color(row, sel_bg if name in self.checked_backups else self.C['card'])

    # ---------------- 视图钩子 ----------------
    def _view_refresh_candidates(self):
        C = self.C
        self._hovered_cand = None
        for w in self.cand_list.winfo_children():
            w.destroy()
        self.cand_rows = {}
        self.cand_checks = {}
        self.checked_candidates = {i for i in self.checked_candidates if 0 <= i < len(self.candidates)}
        if not self.candidates:
            self.cand_list.set_empty_mode(True)
            box = tk.Frame(self.cand_list, bg=C['card'])
            box.place(relx=0.5, rely=0.5, anchor='center')
            tk.Label(box, text='还没有待导入的音源', bg=C['card'], fg=C['muted'],
                     font=self.f_card).pack()
            tk.Label(box, text='可从「官方精选音源库」一键获取，或扫描本地文件夹、从下方订阅「拉取挑选」',
                     bg=C['card'], fg=C['faint'], font=self.f_tiny, justify='center').pack(pady=(6, 12))
            btn_row = tk.Frame(box, bg=C['card'])
            btn_row.pack()
            try:
                self._btn(btn_row, '★ 官方精选音源库', self.do_add_recommended, kind='primary', width=142).pack(
                    side='left', padx=4)
                self._btn(btn_row, '选择本地文件夹', self.do_scan_folder, width=128).pack(
                    side='left', padx=4)
            except Exception:
                pass
        else:
            shown = 0
            for i in range(len(self.candidates)):
                if not self._candidate_visible(i):
                    continue
                shown += 1
                self._build_candidate_row(i)
            if shown == 0:
                self.cand_list.set_empty_mode(True)
                lbl = tk.Label(self.cand_list, text='没有匹配「{}」的音源'.format(self.candidate_filter),
                               bg=C['card'], fg=C['faint'], font=self.f_small)
                lbl.place(relx=0.5, rely=0.5, anchor='center')
            else:
                self.cand_list.set_empty_mode(False)
        self._refresh_count_label()
        self._update_action_buttons()

    def _view_refresh_imported(self):
        C = self.C
        self._hovered_imp = None
        for w in self.imp_list.winfo_children():
            w.destroy()
        self.imp_rows = {}
        self.imp_checks = {}
        self.checked_imported = {i for i in self.checked_imported if 0 <= i < len(self.entries)}
        if not self.entries:
            self.imp_list.set_empty_mode(True)
            box = tk.Frame(self.imp_list, bg=C['card'])
            box.place(relx=0.5, rely=0.5, anchor='center')
            tk.Label(box, text='当前还没有已导入的音源', bg=C['card'], fg=C['muted'], font=self.f_card).pack()
            tk.Label(box, text='在左侧挑选音源后点「导入所选」即可写入洛雪音乐',
                     bg=C['card'], fg=C['faint'], font=self.f_tiny, justify='center').pack(pady=(6, 0))
        else:
            self.imp_list.set_empty_mode(False)
            for i, e in enumerate(self.entries):
                self._build_imported_row(i, e)
        self.imp_count.configure(text='共 {} 个 · 已选 {}'.format(len(self.entries), len(self.checked_imported)))

    def _view_refresh_backups(self):
        C = self.C
        for w in self.bk_list.winfo_children():
            w.destroy()
        self.bk_rows = {}
        files = self.backups.list_files()
        self.checked_backups = {n for n in self.checked_backups if any(f['name'] == n for f in files)}
        if not files:
            self.bk_list.set_empty_mode(True)
            lbl = tk.Label(self.bk_list, text='暂无备份\n每次导入或删除前会自动生成备份',
                           bg=C['card'], fg=C['faint'], font=self.f_tiny,
                           justify='center', wraplength=240)
            lbl.place(relx=0.5, rely=0.5, anchor='center')
            return
        self.bk_list.set_empty_mode(False)
        sel_bg = C.get('row_sel', C['card2'])
        for f in files:
            row_bg = sel_bg if f['name'] in self.checked_backups else C['card']
            row = tk.Frame(self.bk_list, bg=row_bg, cursor='hand2')
            row._cur_bg = row_bg
            row.pack(fill='x', padx=4, pady=1)
            name_l = tk.Label(row, text=short(f['name'], 24), bg=row_bg, fg=C['text'], font=self.f_small,
                              anchor='w', cursor='hand2')
            name_l.pack(side='left', padx=(10, 4), pady=4)
            meta_l = tk.Label(row, text='{:.1f} KB · {}'.format(f['size'] / 1024.0, f['mtime']),
                              bg=row_bg, fg=C['faint'], font=self.f_mono, cursor='hand2')
            meta_l.pack(side='right', padx=8, pady=4)
            for w in (row, name_l, meta_l):
                w.bind('<Button-1>', lambda e, n=f['name'], frm=row: self._bk_toggle(n, frm))

    # ---------------- 订阅行 ----------------
    def _build_sub_row(self, i, sub):
        C = self.C
        is_current = sub.get('repo') == self._current_sub
        sel_bg = C.get('row_sel', C['card2'])
        row_bg = sel_bg if is_current else C['card']
        row = tk.Frame(self.sub_list, bg=row_bg, cursor='hand2')
        row._cur_bg = row_bg
        row.pack(fill='x', padx=6, pady=1)
        def _sub_chk_toggle(idx=i):
            new_st = idx not in self.checked_subs
            self._toggle_sub(idx, new_st)
            self._sync_fast_check(chk, new_st)
        chk = self._make_fast_check(row, i in self.checked_subs, _sub_chk_toggle)
        chk.pack(side='left', padx=(8, 6), pady=5)
        tag = sub.get('last_tag')
        state = sub.get('check_state') or ''
        state_map = {
            'new': (' ↑ 有新版 ', C['card2'], C['accent']),
            'latest': (' ✓ 最新 ', C.get('green_bg', C['field']), C['green']),
            'error': (' ! 失败 ', C.get('danger_bg', C['field']), C['danger']),
        }
        badge_txt, badge_bg, badge_fg = state_map.get(state, ('', C['field'], C['faint']))
        if badge_txt:
            bd = tk.Label(row, text=badge_txt, bg=badge_bg, fg=badge_fg, font=self.f_tiny,
                          padx=4, pady=1, cursor='hand2')
            bd._keep_bg = True
            bd.pack(side='right', padx=(4, 8), pady=4)
        else:
            bd = None
        pull_btn = tk.Label(row, text=' 拉取挑选 ', bg=C['card2'], fg=C['accent'], font=self.f_tiny,
                            padx=5, pady=1, cursor='hand2')
        pull_btn._keep_bg = True
        pull_btn.pack(side='right', padx=(4, 4), pady=4)
        pull_btn.bind('<Button-1>', lambda e, s=sub: self.do_fetch_sub_to_candidates(s))

        inner = tk.Frame(row, bg=row_bg, cursor='hand2')
        inner.pack(side='left', fill='x', expand=True, pady=(2, 2))
        name_l = tk.Label(inner, text=sub.get('repo', ''), bg=row_bg, fg=C['text'],
                          font=self.f_bold, anchor='w', justify='left', cursor='hand2')
        name_l.pack(side='top', fill='x', anchor='w')
        st_l = tk.Label(inner, text=self._sub_meta_text(sub), bg=row_bg,
                        fg=C['green'] if tag else C['faint'], font=self.f_mono,
                        anchor='w', justify='left', cursor='hand2')
        st_l.pack(side='top', fill='x', anchor='w')
        self.sub_rows[i] = row
        row.bind('<Enter>', lambda e, frm=row, cur=is_current: self._sub_enter(frm, cur))
        row.bind('<Leave>', lambda e, frm=row, cur=is_current: self._sub_leave(frm, cur))
        for w in ([row, inner, name_l, st_l] + ([bd] if bd else [])):
            w.bind('<Button-1>', lambda e, s=sub: self.do_show_subscription_sources(s))
            w.bind('<Double-Button-1>', lambda e, s=sub: self.do_update_subscription(s))
            w.bind('<Button-3>', lambda e, idx=i: self.show_sub_menu(e, idx))

    def _sub_enter(self, row, is_current):
        if not is_current:
            self._set_row_color(row, self.C['hover'])

    def _sub_leave(self, row, is_current):
        sel_bg = self.C.get('row_sel', self.C['card2'])
        self._set_row_color(row, sel_bg if is_current else self.C['card'])

    def _view_refresh_subscriptions(self):
        for w in self.sub_list.winfo_children():
            w.destroy()
        self.sub_rows = {}
        self.checked_subs = {i for i in self.checked_subs if 0 <= i < len(self.subscriptions)}
        if not self.subscriptions:
            self.sub_list.set_empty_mode(True)
            C = self.C
            box = tk.Frame(self.sub_list, bg=C['card'])
            box.place(relx=0.5, rely=0.5, anchor='center')
            tk.Label(box, text='还没有订阅音源仓库', bg=C['card'], fg=C['muted'],
                     font=self.f_card).pack()
            tk.Label(box, text='推荐从「官方精选音源库」一键获取活跃单源或订阅主流仓库，支持先拉取到左侧挑选再导入',
                     bg=C['card'], fg=C['faint'], font=self.f_tiny,
                     justify='center', wraplength=360).pack(pady=(4, 8))
            btn_row = tk.Frame(box, bg=C['card'])
            btn_row.pack()
            self._btn(btn_row, '★ 官方精选音源库', self.do_add_recommended, kind='primary', width=142).pack(
                side='left', padx=4)
            self._btn(btn_row, '手动添加仓库…', self.do_add_subscription, width=124).pack(
                side='left', padx=4)
            return
        self.sub_list.set_empty_mode(False)
        for i, sub in enumerate(self.subscriptions):
            self._build_sub_row(i, sub)

    def _view_rebuild_live(self):
        """原地实时重建界面（切换配色方案或缩放字号时无需重启进程，保留全部状态与日志）。"""
        self._close_popover()
        saved_log = ''
        try:
            saved_log = self.logbox.get('1.0', 'end-1c')
        except Exception:
            pass
        saved_mode = self.mode_var.get() if hasattr(self, 'mode_var') else MODE_ADD_LABEL
        saved_filter = self.candidate_filter
        if self._settings_win is not None:
            try:
                self._settings_win.destroy()
            except Exception:
                pass
            self._settings_win = None
        cur_theme_key = self.settings.get('theme') or 'green'
        apply_theme(cur_theme_key)
        self.C = PALETTE
        self.dpi_scale = _dpi_scale()
        self.ui_scale = _ui_scale(self.settings.get('ui_scale')) * self.dpi_scale
        self._effective_scale = self.ui_scale
        dark = cur_theme_key == 'dark'
        try:
            self.ctk.set_appearance_mode('dark' if dark else 'light')
            self.root.configure(fg_color=self.C['bg'])
        except Exception:
            pass
        self._sync_dwm_border_color()
        self.icon = _make_icon(zoom=2, theme='green')
        self._icon_small = _make_icon(zoom=1, theme=cur_theme_key)
        _apply_taskbar_and_window_icon(self.root, self.icon)
        for child in list(self.root.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self._build()
        try:
            self.mode_var.set(saved_mode)
            self._set_mode(saved_mode)
            self._sync_mode_pills()
            if saved_filter:
                self.search_entry.delete(0, 'end')
                self.search_entry.insert(0, saved_filter)
                self.search_entry.configure(fg=self.C['text'])
                self.search_var.set(saved_filter)
        except Exception:
            pass
        self._view_refresh_imported()
        self._view_refresh_candidates()
        self._view_refresh_backups()
        self._view_refresh_subscriptions()
        self.apply_settings()
        if saved_log:
            try:
                self.logbox.configure(state='normal')
                self.logbox.delete('1.0', 'end')
                for ln in saved_log.splitlines():
                    lvl = 'info'
                    if '[成功]' in ln:
                        lvl = 'ok'
                    elif '[更新]' in ln:
                        lvl = 'update'
                    elif '[提示]' in ln or '[跳过]' in ln:
                        lvl = 'warn'
                    elif '[错误]' in ln:
                        lvl = 'error'
                    self.logbox.insert('end', ln + '\n', lvl)
                self.logbox.see('end')
                self.logbox.configure(state='disabled')
            except Exception:
                pass

    def _view_input(self, title, prompt, password=False):
        ctk, C = self.ctk, self.C
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(title)
        dlg.configure(fg_color=C['card'])
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        ctk.CTkLabel(dlg, text=prompt, wraplength=420, justify='left', font=self.f_base,
                     text_color=C['text']).pack(padx=22, pady=(18, 10), anchor='w')
        entry = ctk.CTkEntry(dlg, width=380, height=32, corner_radius=8, fg_color=C['field'],
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
        self._btn(btns, '取消', dlg.destroy, width=92).pack(side='left', padx=6)
        self._btn(btns, '确定', ok, kind='primary', width=92).pack(side='left', padx=6)
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
            if hasattr(self, 'mirror_var'):
                cur_m = (self.settings.get('mirror') or '').strip()
                disp = '直连 (官方)' if not cur_m else cur_m.replace('https://', '').replace('http://', '').strip('/')
                self.mirror_var.set(disp)
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
        win.title('偏好设置')
        win.configure(fg_color=C['bg'])
        win.resizable(False, False)
        win.transient(self.root)
        win.protocol('WM_DELETE_WINDOW', self._on_settings_close)
        win.grid_columnconfigure(0, weight=1)

        def sec(title, row):
            f = ctk.CTkFrame(win, fg_color=C['card'], corner_radius=12,
                             border_width=1, border_color=C.get('card_border', C['border']))
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

        # ---- 一、外观与行为 ----
        f0 = sec('一、外观与行为', 0)
        wlab(f0, 1, '配色方案', 0)
        theme_row = ctk.CTkFrame(f0, fg_color='transparent')
        theme_row.grid(row=1, column=1, columnspan=3, sticky='w', padx=(0, 14), pady=4)
        self.cfg_theme_var = tk.StringVar(value=THEMES.get(self.settings.get('theme') or 'green', THEMES['green'])['label'])
        self.cfg_theme_menu = self._select_btn(
            theme_row, self.cfg_theme_var, [THEMES[k]['label'] for k in THEME_ORDER],
            lambda label: self.do_set_theme(next((k for k in THEME_ORDER if THEMES[k]['label'] == label), 'green')),
            width=156)
        self.cfg_theme_menu.pack(side='left')
        wsub(f0, 2, '内置清风（洛雪，默认）、暖砂（类Claude）、鲸蓝（类Deepseek）、星月（暗夜），切换后立即生效')

        wlab(f0, 3, '界面字号', 0)
        scale_row = ctk.CTkFrame(f0, fg_color='transparent')
        scale_row.grid(row=3, column=1, columnspan=3, sticky='w', padx=(0, 14), pady=4)
        self.cfg_scale_var = tk.DoubleVar(value=float(self.settings.get('ui_scale') or 1.0))
        self.cfg_scale_slider = ctk.CTkSlider(
            scale_row, from_=UI_SCALE_MIN, to=UI_SCALE_MAX, number_of_steps=15,
            width=220, height=18, variable=self.cfg_scale_var,
            fg_color=C['field'], progress_color=C['accent'], button_color=C['accent'],
            button_hover_color=C['accent_hover'],
            command=lambda v: self.cfg_scale_label.configure(text='{:.0%}'.format(float(v))))
        self.cfg_scale_slider.pack(side='left', padx=(0, 10))
        self.cfg_scale_label = ctk.CTkLabel(scale_row, text='{:.0%}'.format(float(self.cfg_scale_var.get())),
                                            font=self.f_mono, text_color=C['text'], width=46)
        self.cfg_scale_label.pack(side='left', padx=(0, 10))
        self._btn(scale_row, '立即应用', lambda: self.do_set_ui_scale(self.cfg_scale_var.get()), width=84).pack(side='left')
        wsub(f0, 4, '觉得字太小可调大（85% ~ 200%，全屏还会自动叠加放大），点击「立即应用」或顶栏「字号」即时生效')

        wlab(f0, 5, '洛雪程序', 0)
        self.cfg_lx_label = ctk.CTkLabel(
            f0, text=short_path(self.settings.get('lx_path') or find_lx_music_path() or '未探测到',
                                44), font=self.f_mono, text_color=C['muted'], anchor='w')
        self.cfg_lx_label.grid(row=5, column=1, columnspan=2, sticky='w', padx=(0, 8), pady=4)
        self._btn(f0, '选择…', self.set_lx_music_path, width=72).grid(row=5, column=3, sticky='w', padx=(0, 14), pady=4)
        wsub(f0, 6, '用于顶栏「重启洛雪」按钮；不指定时自动在常见安装位置查找')

        # ---- 二、备份配置 ----
        f1 = sec('二、备份配置', 1)
        self.cfg_backup_var = tk.BooleanVar(value=self.settings.get('backup_enabled', True))
        wcheck(f1, 1, self.cfg_backup_var, '自动备份（每次写操作前备份；关闭后隐藏备份模块）',
               lambda: self.do_set_backup_enabled(self.cfg_backup_var.get()))
        wlab(f1, 2, '备份文件夹', 0)
        self.cfg_backup_entry = wentry(f1, 2, effective_backup_dir(self.settings),
                                       self.do_set_backup_dir)
        self._btn(f1, '浏览…', lambda: self._pick_dir_to(self.cfg_backup_entry, self.do_set_backup_dir),
                  width=68).grid(row=2, column=2, padx=(0, 14), pady=4)
        wsub(f1, 3, '更改目录时可将旧备份迁移到新位置')

        # ---- 三、订阅配置 ----
        f2 = sec('三、订阅配置', 2)
        wlab(f2, 1, '下载目录', 0)
        self.cfg_dl_entry = wentry(f2, 1, effective_download_dir(self.settings),
                                   self.do_set_download_dir)
        self._btn(f2, '浏览…', lambda: self._pick_dir_to(self.cfg_dl_entry, self.do_set_download_dir),
                  width=68).grid(row=1, column=2, padx=(0, 14), pady=4)
        wsub(f2, 2, '每个订阅存放于 下载目录/<仓库名>/ 子文件夹；zip 自动解压，旧版本归档到 history/')
        wlab(f2, 3, '下载方式', 0)
        self.cfg_dl_var = tk.StringVar(value=self.DL_LABELS.get(self.settings.get('downloader', 'auto'), '自动'))
        self.cfg_dl_menu = self._select_btn(
            f2, self.cfg_dl_var, list(self.DL_LABELS.values()), self._on_downloader_pick, width=108)
        self.cfg_dl_menu.grid(row=3, column=1, sticky='w', padx=(0, 8), pady=4)
        self.cfg_dl_status = ctk.CTkLabel(f2, text=self._downloader_status_text(), font=self.f_mono,
                                          text_color=C['faint'], anchor='w')
        self.cfg_dl_status.grid(row=3, column=2, sticky='w', padx=(0, 10), pady=4)
        self._btn(f2, '测试 ABDM', self.do_test_abdm, width=88).grid(row=3, column=3, padx=(0, 8), pady=4)
        self._btn(f2, '指定 ABDM…', self.do_pick_abdm, width=96).grid(row=3, column=4, padx=(0, 14), pady=4)
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
        self._btn(f2, '打开文件夹', self._open_cfg_sub_dir, width=88).grid(
            row=6, column=1, sticky='w', padx=(0, 8), pady=(0, 10))
        self._btn(f2, '删除订阅', self._delete_cfg_sub, width=88).grid(
            row=6, column=2, sticky='w', padx=(0, 14), pady=(0, 10))

        # ---- 四、日志配置 ----
        f3 = sec('四、日志配置', 3)
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
        bottom_row.grid(row=4, column=0, sticky='e', padx=16, pady=12)
        self._btn(bottom_row, '关闭', self._on_settings_close, width=88, kind='primary').pack(side='left')
        try:
            win.update_idletasks()
            w = max(640, win.winfo_reqwidth() + 30)
            h = win.winfo_reqheight() + 12
            x = self.root.winfo_rootx() + max((self.root.winfo_width() - w) // 2, 0)
            y = self.root.winfo_rooty() + max((self.root.winfo_height() - h) // 2, 0)
            win.geometry('{}x{}+{}+{}'.format(w, h, x, y))
        except Exception:
            pass

    def _view_rebalance_bottom(self):
        try:
            show_bk = self.settings.get('backup_enabled', True)
            show_lg = self.settings.get('log_enabled', True) and self.settings.get('log_window', True)
            cards = []
            weights = []
            minsizes = []
            if show_bk:
                cards.append(self._bk_card)
                weights.append(3)
                minsizes.append(250)
            cards.append(self._sub_card)
            weights.append(5)
            minsizes.append(380)
            if show_lg:
                cards.append(self._lg_card)
                weights.append(4)
                minsizes.append(280)
            for i, card in enumerate(cards):
                left = 0 if i == 0 else 5
                right = 0 if i == len(cards) - 1 else 5
                card.grid(row=0, column=i, sticky='nsew', padx=(left, right))
            for i in range(3):
                w = weights[i] if i < len(weights) else 0
                ms = minsizes[i] if i < len(minsizes) else 0
                self._bottom.grid_columnconfigure(i, weight=w, minsize=ms, uniform='')
        except Exception:
            pass

    def _view_refresh_cfg_logwin(self):
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
        text = text or self.STATUS_HINT
        self.status_var.set(text)
        try:
            self.status_label.configure(
                text_color=self.C['faint'] if text == self.STATUS_HINT else self.C['muted'])
        except Exception:
            pass

    def _view_set_progress(self, frac, text):
        """显示/隐藏下载进度条：frac=None 隐藏；0 表示不确定长度用跑马灯。"""
        try:
            if frac is None:
                try:
                    self.prog_bar.stop()
                except Exception:
                    pass
                self.prog_row.grid_remove()
                return
            self.prog_row.grid()
            if frac <= 0:
                self.prog_bar.set(0)
                self.prog_bar.configure(mode='indeterminate')
                try:
                    self.prog_bar.start()
                except Exception:
                    pass
            else:
                try:
                    self.prog_bar.stop()
                except Exception:
                    pass
                self.prog_bar.configure(mode='determinate')
                self.prog_bar.set(min(1.0, max(0.0, frac)))
            self.prog_text.configure(text=text or '')
        except Exception:
            pass

    def _on_root_configure(self, event):
        """窗口缩放防抖处理：由专属 RootOnly bindtag 触发，拖拽期间不重算字体树，停止拖拽后统一自适应。"""
        if event.widget is not self.root:
            return
        self._close_popover()
        new_sz = (event.width, event.height)
        if new_sz == getattr(self, '_last_root_size', None):
            return
        self._last_root_size = new_sz
        if self._resize_after is not None:
            try:
                self.root.after_cancel(self._resize_after)
            except Exception:
                pass
        self._resize_after = self.root.after(150, self._after_resize)

    def _after_resize(self):
        self._resize_after = None
        try:
            win_w = self.root.winfo_width()
            # 小屏下自动精简顶栏主标题文案，防止挤压右侧按钮
            if hasattr(self, '_title_lbl') and self._title_lbl.winfo_exists():
                short_t = 'LX 音源管理' if win_w < 1160 else 'LX Music 音源管理工具'
                if self._title_lbl.cget('text') != short_t:
                    self._title_lbl.configure(text=short_t)
            for name in ('cand_list', 'imp_list', 'bk_list', 'sub_list'):
                lst = getattr(self, name, None)
                if lst is not None:
                    try:
                        lst._flush_canvas_fit()
                    except Exception:
                        pass
        except Exception:
            pass

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
            self._btn(btns, '取消', dlg.destroy, width=92).pack(side='left', padx=6)
            self._btn(btns, '确定', ok, kind=('danger' if danger else 'primary'), width=92).pack(side='left', padx=6)
        else:
            self._btn(btns, '知道了', dlg.destroy, kind='primary', width=96).pack(side='left', padx=6)
        dlg.protocol('WM_DELETE_WINDOW', dlg.destroy)
        try:
            dlg.after(10, lambda: dlg.iconphoto(False, self.icon))
        except Exception:
            pass
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
        _s = load_settings()
        apply_theme(_s.get('theme') or 'green')
        self.C = PALETTE
        self.dpi_scale = _dpi_scale()
        self.ui_scale = _ui_scale(_s.get('ui_scale')) * self.dpi_scale
        self.animations = not hidden
        self.settings = _s
        set_mirror(self.settings['mirror'])
        self.use_idm = self.settings['use_idm']
        self.idm_path = find_idm_path()
        self.abdm_path = self.settings.get('abdm_path') or find_abdm_path()
        self.root = tk.Tk()
        if hidden:
            self.root.withdraw()
        self.root.title(APP_TITLE)
        w, h = _initial_size(self.ui_scale)
        self.root.geometry('{}x{}'.format(w, h))
        _mw, _mh = _min_size(self.ui_scale)
        self.root.minsize(_mw, _mh)
        self.root.configure(bg=self.C['bg'])
        self.icon = _make_icon(zoom=2, theme='green')
        _apply_taskbar_and_window_icon(self.root, self.icon)
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
        sz = _scale_fonts(self.ui_scale, FONT_BASE)
        self.font_sizes = sz
        # ttk 界面用普通元组字体，名字与 CTk 界面保持一致，公共对话框才两边通用
        self.f_card = (F, sz['card'], 'bold')
        self.f_bold = (F, sz['bold'], 'bold')
        self.f_base = (F, sz['base'])
        self.f_small = (F, sz['small'])
        self.f_tiny = (F, sz['tiny'])
        self.f_btn = (F, sz['btn'])
        s.configure('.', background=C['bg'], foreground=C['text'], fieldbackground=C['field'],
                    bordercolor=C['border'], lightcolor=C['border'], darkcolor=C['border'],
                    troughcolor=C['field'], font=(F, sz['small']))
        s.configure('TFrame', background=C['bg'])
        s.configure('Card.TFrame', background=C['card'])
        s.configure('TLabel', background=C['bg'], foreground=C['text'])
        s.configure('Card.TLabel', background=C['card'], foreground=C['text'])
        s.configure('CardTitle.TLabel', background=C['card'], foreground=C['text'],
                    font=(F, sz['card'], 'bold'))
        s.configure('Muted.TLabel', background=C['card'], foreground=C['muted'], font=(F, sz['tiny']))
        s.configure('Status.TLabel', background=C['bg'], foreground=C['faint'], font=(F, sz['tiny']))
        s.configure('TButton', background=C['card2'], foreground=C['text'], borderwidth=0,
                    focusthickness=0, padding=(10, 5), font=(F, sz['small']))
        s.map('TButton', background=[('active', C['hover']), ('pressed', C['card2'])],
              foreground=[('active', C['text'])])
        s.configure('Accent.TButton', background=C['accent'], foreground=PALETTE['on_accent'], borderwidth=0,
                    focusthickness=0, padding=(12, 5), font=(F, sz['small']))
        s.map('Accent.TButton', background=[('active', C['accent_hover']), ('pressed', C['accent'])],
              foreground=[('active', PALETTE['on_accent'])])
        s.configure('Danger.TButton', background=C['danger'], foreground=PALETTE['on_accent'], borderwidth=0,
                    focusthickness=0, padding=(12, 5), font=(F, 10))
        s.map('Danger.TButton', background=[('active', '#e56a6f')], foreground=[('active', PALETTE['on_accent'])])
        s.configure('TEntry', fieldbackground=C['field'], foreground=C['text'], insertcolor=C['text'],
                    bordercolor=C['border'], lightcolor=C['border'], darkcolor=C['border'], padding=5)
        s.configure('Treeview', background=C['field'], fieldbackground=C['field'], foreground=C['text'],
                    rowheight=int(26 * self.ui_scale), borderwidth=0, font=(F, sz['small']))
        s.map('Treeview', background=[('selected', C['accent'])], foreground=[('selected', PALETTE['on_accent'])])
        s.configure('Treeview.Heading', background=C['card2'], foreground=C['text'], borderwidth=0,
                    font=(F, sz['small'], 'bold'), padding=4)
        s.map('Treeview.Heading', background=[('active', C['hover'])])
        s.configure('TRadiobutton', background=C['card'], foreground=C['text'], font=(F, sz['small']))
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
        ttk.Button(header, text='重启洛雪', command=self.do_restart_lx_music).grid(row=0, column=2, rowspan=2, sticky='e', padx=(0, 4))
        ttk.Button(header, text='检查更新', command=self.do_check_app_update).grid(row=0, column=3, rowspan=2, sticky='e', padx=(0, 4))
        ttk.Button(header, text='外观设置', command=self.do_open_settings).grid(row=0, column=4, rowspan=2, sticky='e', padx=(0, 4))
        ttk.Button(header, text='重新定位', command=self.do_relocate).grid(row=0, column=5, rowspan=2, sticky='e', padx=(0, 4))
        ttk.Button(header, text='打开数据目录', command=self.do_open_data_dir).grid(row=0, column=6, rowspan=2, sticky='e', padx=(4, 0))

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
        ttk.Button(bar, text='智能勾选', command=self.do_smart_select).pack(side='left', padx=2)
        ttk.Button(bar, text='全选', command=lambda: self.do_select_all_candidates(True)).pack(side='left', padx=2)
        ttk.Button(bar, text='全不选', command=lambda: self.do_select_all_candidates(False)).pack(side='left', padx=2)
        ttk.Button(bar, text='移除所选', command=self.do_remove_candidates).pack(side='left', padx=2)
        ttk.Button(bar, text='清空列表', command=self.do_clear_candidates).pack(side='left', padx=2)
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', lambda *a: self._on_search())
        self.search_entry = ttk.Entry(left, textvariable=self.search_var)
        self.search_entry.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(2, 4))
        self._setup_placeholder(self.search_entry, BaseApp.SEARCH_HINT)
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
                                 selectforeground=PALETTE['on_accent'], relief='flat', highlightthickness=0,
                                 font=(FONT_FAMILY, self.font_sizes['small']), height=5,
                                 selectmode='extended', exportselection=False)
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
        ttk.Button(sbtns, text='★ 精选源库', style='Accent.TButton', command=self.do_add_recommended).pack(side='left', padx=2)
        ttk.Button(sbtns, text='＋ 添加', command=self.do_add_subscription).pack(side='left', padx=2)
        ttk.Button(sbtns, text='检查', command=self.do_check_subscriptions).pack(side='left', padx=2)
        ttk.Button(sbtns, text='拉取挑选', command=lambda: self.do_fetch_sub_to_candidates(None)).pack(side='left', padx=2)
        ttk.Button(sbtns, text='一键更新', command=self.do_update_all_subscriptions).pack(side='left', padx=2)
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

    def _view_rebuild_live(self):
        """ttk 界面原地重建（切换主题或字号时无需重启）。"""
        cur_theme_key = self.settings.get('theme') or 'green'
        apply_theme(cur_theme_key)
        self.C = PALETTE
        self.dpi_scale = _dpi_scale()
        self.ui_scale = _ui_scale(self.settings.get('ui_scale')) * self.dpi_scale
        self.root.configure(bg=self.C['bg'])
        self.icon = _make_icon(zoom=2, theme='green')
        _apply_taskbar_and_window_icon(self.root, self.icon)
        self._init_style()
        for child in list(self.root.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self._build()
        self._view_refresh_imported()
        self._view_refresh_candidates()
        self._view_refresh_backups()
        self._view_refresh_subscriptions()
        self.apply_settings()

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
def _render_brand_icon_pil(size=64, theme=None):
    """用 PIL 4x 超采样绘制品牌圆角徽章 RGBA Image：
    - green（清风·洛雪）：翠绿双八分音符 + 六角雪晶徽章（默认主题，同时用作 EXE 与任务栏图标）
    - claude（暖砂·类Claude）：暖砂十二芒星徽章
    - ocean（鲸蓝·类Deepseek）：灵动蓝鲸喷水徽章
    - dark（星月·暗夜）：星夜靛蓝底板 + 银蓝弯月与星辰徽章
    """
    import math
    from PIL import Image, ImageDraw
    theme_key = theme or PALETTE.get('_theme_key', 'green')
    theme_dict = THEMES.get(theme_key) or PALETTE
    ss = 4 if size <= 64 else 2
    S = size * ss
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(2, int(size * 0.06 * ss))
    rad = int(size * 0.28 * ss)
    accent_rgb = hex_rgb(theme_dict.get('accent', '#2b7a56')) + (255,)
    fg_rgb = hex_rgb(theme_dict.get('on_accent', '#ffffff')) + (255,)
    cx, cy = S / 2.0, S / 2.0

    if theme_key == 'dark':
        # 星夜：深邃星夜蓝底板 + 柔和星光蓝边框 + 银蓝弯月与双星
        bg_rgb = (27, 30, 42, 255)
        bdr_rgb = (110, 130, 245, 220)
        moon_rgb = (224, 232, 255, 255)
        d.rounded_rectangle((pad, pad, S - pad - 1, S - pad - 1), radius=rad,
                            fill=bg_rgb, outline=bdr_rgb, width=max(2, int(1.3 * ss * (size / 28.0))))
        moon_layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
        md = ImageDraw.Draw(moon_layer)
        r_outer = S * 0.27
        mx, my = S * 0.47, S * 0.52
        md.ellipse((mx - r_outer, my - r_outer, mx + r_outer, my + r_outer), fill=moon_rgb)
        r_cut = S * 0.23
        cx_cut, cy_cut = S * 0.59, S * 0.41
        md.ellipse((cx_cut - r_cut, cy_cut - r_cut, cx_cut + r_cut, cy_cut + r_cut), fill=(0, 0, 0, 0))
        img.alpha_composite(moon_layer)
        d = ImageDraw.Draw(img)
        w_star = max(2, int(1.4 * ss * (size / 28.0)))
        for sx, sy, sr in ((S * 0.68, S * 0.29, S * 0.055), (S * 0.75, S * 0.48, S * 0.038)):
            d.line([(sx - sr, sy), (sx + sr, sy)], fill=moon_rgb, width=w_star)
            d.line([(sx, sy - sr), (sx, sy + sr)], fill=moon_rgb, width=w_star)

    elif theme_key == 'green':
        # 洛雪（清风）：翠绿圆角底板 + 双连音符 ♫ + 左上洛雪六角雪晶
        d.rounded_rectangle((pad, pad, S - pad - 1, S - pad - 1), radius=rad, fill=accent_rgb)
        stem_w = max(3, int(2.2 * ss * (size / 28.0)))
        x1, y1_bot, y1_top = S * 0.41, S * 0.67, S * 0.30
        x2, y2_bot, y2_top = S * 0.72, S * 0.61, S * 0.24
        d.line([(x1, y1_bot), (x1, y1_top)], fill=fg_rgb, width=stem_w)
        d.line([(x2, y2_bot), (x2, y2_top)], fill=fg_rgb, width=stem_w)
        d.polygon([
            (x1 - stem_w * 0.4, y1_top),
            (x2 + stem_w * 0.4, y2_top),
            (x2 + stem_w * 0.4, y2_top + S * 0.085),
            (x1 - stem_w * 0.4, y1_top + S * 0.085),
        ], fill=fg_rgb)
        nh_rx, nh_ry = S * 0.095, S * 0.072
        d.ellipse((x1 - nh_rx * 1.4, y1_bot - nh_ry, x1 + nh_rx * 0.5, y1_bot + nh_ry), fill=fg_rgb)
        d.ellipse((x2 - nh_rx * 1.4, y2_bot - nh_ry, x2 + nh_rx * 0.5, y2_bot + nh_ry), fill=fg_rgb)
        # 左上角洛雪六角雪晶点缀
        lx_x, lx_y, lx_r = S * 0.26, S * 0.31, S * 0.065
        snow_w = max(2, int(1.3 * ss * (size / 28.0)))
        for deg in (0, 60, 120):
            a = math.radians(deg)
            d.line([
                (lx_x - math.cos(a) * lx_r, lx_y - math.sin(a) * lx_r),
                (lx_x + math.cos(a) * lx_r, lx_y + math.sin(a) * lx_r),
            ], fill=fg_rgb, width=snow_w)

    elif theme_key == 'ocean':
        # 鲸蓝（DeepSeek）：深海蓝底板 + 灵动小鲸鱼（饱满鲸身 + 上扬双尾鳍 + 眼睛 + 水柱水滴）
        d.rounded_rectangle((pad, pad, S - pad - 1, S - pad - 1), radius=rad, fill=accent_rgb)
        d.ellipse((S * 0.17, S * 0.39, S * 0.66, S * 0.74), fill=fg_rgb)
        d.polygon([
            (S * 0.50, S * 0.69),
            (S * 0.74, S * 0.42),
            (S * 0.79, S * 0.46),
            (S * 0.62, S * 0.72),
        ], fill=fg_rgb)
        d.polygon([
            (S * 0.74, S * 0.45),
            (S * 0.65, S * 0.28),
            (S * 0.76, S * 0.34),
            (S * 0.86, S * 0.30),
            (S * 0.79, S * 0.46),
        ], fill=fg_rgb)
        d.polygon([
            (S * 0.40, S * 0.68),
            (S * 0.49, S * 0.81),
            (S * 0.53, S * 0.70),
        ], fill=fg_rgb)
        er = S * 0.034
        ex, ey = S * 0.31, S * 0.53
        d.ellipse((ex - er, ey - er, ex + er, ey + er), fill=accent_rgb)
        for wx, wy, wr in ((S * 0.35, S * 0.27, S * 0.032), (S * 0.44, S * 0.22, S * 0.026)):
            d.ellipse((wx - wr, wy - wr, wx + wr, wy + wr), fill=fg_rgb)

    else:
        # 暖砂（Claude）：经典十二芒星徽章
        d.rounded_rectangle((pad, pad, S - pad - 1, S - pad - 1), radius=rad, fill=accent_rgb)
        rays = [
            (0, 0.34, 2.2), (28, 0.29, 1.9), (62, 0.33, 2.1),
            (92, 0.30, 1.8), (125, 0.34, 2.2), (156, 0.28, 1.8),
            (184, 0.33, 2.1), (214, 0.30, 1.9), (246, 0.34, 2.2),
            (278, 0.29, 1.8), (310, 0.33, 2.1), (338, 0.28, 1.9),
        ]
        for deg, length_frac, w_mult in rays:
            ang = math.radians(deg - 12)
            r0 = S * 0.055
            r1 = S * length_frac
            x0 = cx + math.cos(ang) * r0
            y0 = cy + math.sin(ang) * r0
            x1 = cx + math.cos(ang) * r1
            y1 = cy + math.sin(ang) * r1
            d.line([(x0, y0), (x1, y1)], fill=fg_rgb, width=max(2, int(w_mult * ss * (size / 28.0))), joint='curve')
        d.ellipse((cx - S * 0.08, cy - S * 0.08, cx + S * 0.08, cy + S * 0.08), fill=fg_rgb)

    return img.resize((size, size), Image.Resampling.LANCZOS)


def _make_icon(zoom=2, theme=None):
    """生成 Tkinter PhotoImage 图标（zoom=1 用于顶栏 28px 徽章，zoom=2 用于 36px 窗口图标）。"""
    size = 28 if zoom == 1 else 36
    try:
        from PIL import ImageTk
        return ImageTk.PhotoImage(_render_brand_icon_pil(size=size, theme=theme))
    except Exception:
        img = tk.PhotoImage(width=24, height=24)
        img.put(PALETTE['accent'], to=(2, 2, 21, 21))
        for d_i in range(5):
            y0, y1 = 12 - d_i, 12 + d_i
            x1 = 8 + 2 * (4 - d_i)
            img.put(PALETTE['on_accent'], to=(8, y0, x1, y1))
        return img


_CACHED_LX_ICO_PATH = None


def _ensure_lx_ico():
    """确保磁盘上存在『洛雪（green）』主题的多尺寸 .ico 图标文件：
    1. 供运行期窗口与 Windows 任务栏使用（固定为洛雪图标，不随界面主题改变）
    2. 供 PyInstaller 打包 exe 时直接作为 `--icon=lx_icon.ico` 使用
    """
    global _CACHED_LX_ICO_PATH
    if _CACHED_LX_ICO_PATH and os.path.isfile(_CACHED_LX_ICO_PATH):
        return _CACHED_LX_ICO_PATH
    candidates = [
        os.path.join(tool_dir(), 'lx_icon.ico'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lx_icon.ico'),
    ]
    for p in candidates:
        if os.path.isfile(p) and os.path.getsize(p) > 512:
            _CACHED_LX_ICO_PATH = p
            return p
    try:
        base_img = _render_brand_icon_pil(size=256, theme='green')
        target = candidates[0]
        try:
            base_img.save(
                target,
                format='ICO',
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
            )
            _CACHED_LX_ICO_PATH = target
            return target
        except Exception:
            import tempfile
            fallback = os.path.join(tempfile.gettempdir(), 'lxmusic_source_manager_lx.ico')
            base_img.save(
                fallback,
                format='ICO',
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)],
            )
            _CACHED_LX_ICO_PATH = fallback
            return fallback
    except Exception:
        return None


def _apply_taskbar_and_window_icon(root, photo_icon=None):
    """将窗口图标和任务栏图标固定设置为『洛雪』主题图标。"""
    ico_path = _ensure_lx_ico()
    if ico_path:
        try:
            root.iconbitmap(default=ico_path)
        except Exception:
            try:
                root.iconbitmap(ico_path)
            except Exception:
                pass
    if photo_icon is not None:
        try:
            root.iconphoto(True, photo_icon)
        except Exception:
            pass


def _apply_win32_hwnd_icon(hwnd):
    """通过 Win32 WM_SETICON 显式绑定洛雪 .ico 到顶层 HWND，确保无边框窗口任务栏图标始终为洛雪图标。"""
    if sys.platform != 'win32' or not hwnd:
        return
    ico_path = _ensure_lx_ico()
    if not ico_path:
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        LR_DEFAULTSIZE = 0x0040
        WM_SETICON = 0x0080
        hicon_big = user32.LoadImageW(0, ico_path, IMAGE_ICON, 48, 48, LR_LOADFROMFILE)
        hicon_small = user32.LoadImageW(0, ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if not hicon_big:
            hicon_big = user32.LoadImageW(0, ico_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if hicon_big:
            user32.SendMessageW(hwnd, WM_SETICON, 1, hicon_big)
        if hicon_small:
            user32.SendMessageW(hwnd, WM_SETICON, 0, hicon_small)
    except Exception:
        pass


def _enable_dpi_awareness():
    if sys.platform == 'win32':
        try:
            import ctypes
            try:
                # 独立 AppUserModelID 确保 Windows 任务栏显示本程序的洛雪图标而非 Python 默认图标
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('lxmusic.source.manager.v2')
            except Exception:
                pass
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
    _mod = sys.modules[__name__]
    _mod.subscriptions_path = lambda: os.path.join(tmp, 'subscriptions.json')
    _mod.settings_path = lambda: os.path.join(tmp, 'settings.json')
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
        _meta = parse_script_meta('/*!' + chr(10) + ' * @name 新源' + chr(10) + ' * @version 1.0'
                                 + chr(10) + ' */' + chr(10) + ';(function(){})()')
        _demo = apply_imports([], [SourceScript('/tmp/x.js', 'x.js', 'aa', _meta, 'utf-8', False)], 'add')
        assert len(_demo['added']) == 1 and _demo['added'][0][0].name == '新源', 'report[added] 应为 (s,) 一元组'
        assert version_key('v9.3') > version_key('v4.1'), '版本号比较异常'
        assert version_key('260925') > version_key('260809'), '日期式版本比较异常'
        # 主题体系：四套配色键齐全，默认清风（洛雪），切换后 PALETTE 原地同步
        assert THEME_ORDER == ['green', 'claude', 'ocean', 'dark'] and DEFAULT_SETTINGS['theme'] == 'green'
        for _k in THEME_ORDER:
            assert set(THEMES[_k]) >= set(THEMES['green']), '主题 {} 缺少配色键'.format(_k)
        apply_theme('dark')
        assert PALETTE['bg'] == THEMES['dark']['bg'] and PALETTE['text'] == THEMES['dark']['text']
        assert LOG_COLORS['error'] == THEMES['dark']['danger']
        apply_theme('ocean')
        assert PALETTE['bg'] == THEMES['ocean']['bg']
        apply_theme('claude')
        assert PALETTE['bg'] == THEMES['claude']['bg']
        apply_theme('green')
        assert PALETTE['bg'] == THEMES['green']['bg'], '主题回切失败'
        assert len(RECOMMENDED_DIRECT_SOURCES) >= 6, '精选单源数量不足'
        assert len(RECOMMENDED_SOURCES) >= 5 and RECOMMENDED_SOURCES[0][1] == 'guoyue2010/lxmusic-'
        assert _ui_scale(9) == UI_SCALE_MAX and _ui_scale(0.1) == UI_SCALE_MIN and _ui_scale('1.2') == 1.2
        assert human_size(2048) == '2.0 KB' and human_size(1536 * 1024) == '1.5 MB'
        # 智能勾选：新音源要选、同版跳过、更高版本跳过、更低版本可选
        _lab = dict(name='对比源', version='2.0', author='', description='', homepage='')
        _cands = [SourceScript('/t/a.js', 'a.js', 'aa', dict(_lab), 'utf-8', False),
                  SourceScript('/t/b.js', 'b.js', 'bb', dict(_lab, name='新源'), 'utf-8', False),
                  SourceScript('/t/c.js', 'c.js', 'cc', dict(_lab, name='对比源', version='1.0'), 'utf-8', False)]
        _ctx = BaseApp.__new__(BaseApp)
        _ctx.candidates = _cands
        _ctx.entries = [{'name': '对比源', 'version': '2.0', 'script': compress_script(_cands[0].raw)}]
        _ctx.candidate_filter = ''
        _st_a = _ctx._cand_state(0)
        _st_b = _ctx._cand_state(1)
        _st_c = _ctx._cand_state(2)
        assert _st_a[0] == '=' and _st_a[3] is False, '同版应判为无需导入'
        assert _st_b[0] == '新' and _st_b[3] is True, '新音源应判为需要导入'
        assert _st_c[0] == '↓' and _st_c[3] is False, '低版本应判为无需导入'
        _ctx.entries = [{'name': '对比源', 'version': '1.0', 'script': ''}]
        _st_a2 = _ctx._cand_state(0)
        assert _st_a2[0] == '↑' and _st_a2[3] is True, '可升级应判为需要导入'
        report.append('核心逻辑 OK（扫描/解析/导入/更新/去重/备份/读写/主题/智能勾选）')

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
                    # 导入模式胶囊：「仅新增 / 同名更新」两档都必须可选且真正切换业务状态
                    app._switch_import_mode(MODE_UPDATE_LABEL)
                    app.root.update_idletasks()
                    assert app.import_mode == 'update', '「同名更新」未能切换（import_mode=%r）' % app.import_mode
                    assert app.mode_var.get() == MODE_UPDATE_LABEL
                    assert app.btn_import_sel.cget('text').startswith('更新所选')
                    app._switch_import_mode(MODE_ADD_LABEL)
                    app.root.update_idletasks()
                    assert app.import_mode == 'add', '「仅新增」未能切换（import_mode=%r）' % app.import_mode
                    assert app.btn_import_sel.cget('text').startswith('导入所选')
                    # 同名但内容不同：仅新增模式应真的追加同名副本
                    _dup_meta = parse_script_meta('/*!' + chr(10) + ' * @name 已存在源' + chr(10)
                                                  + ' * @version 9.0.0' + chr(10) + ' */' + chr(10) + ';(function(){})()')
                    _dup = SourceScript('/t/dup.js', 'dup.js', 'zz', _dup_meta, 'utf-8', False)
                    _ent = [dict(base_entry)]
                    _r_add = apply_imports(_ent, [_dup], 'add')
                    assert len(_r_add['added']) == 1 and len(_ent) == 2, '仅新增应追加同名副本'
                    _r_upd = apply_imports([dict(base_entry)], [_dup], 'update')
                    assert len(_r_upd['updated']) == 1
                    # 实时主题切换与字号切换测试
                    app.do_set_theme('ocean')
                    app.root.update_idletasks()
                    assert app.C['bg'] == THEMES['ocean']['bg']
                    app.do_set_theme('claude')
                    app.root.update_idletasks()
                    assert app.C['bg'] == THEMES['claude']['bg']
                    app.do_set_theme('green')
                    app.root.update_idletasks()
                    assert app.C['bg'] == THEMES['green']['bg']
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
            # ttk 回退界面：radiobutton 同样要把「同名更新」映射为 update 模式
            app2.mode_var.set(MODE_UPDATE_LABEL)
            app2._set_mode(app2.mode_var.get())
            assert app2.import_mode == 'update', 'ttk 下「同名更新」未生效'
            app2.mode_var.set(MODE_ADD_LABEL)
            app2._set_mode(app2.mode_var.get())
            assert app2.import_mode == 'add', 'ttk 下「仅新增」未生效'
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
