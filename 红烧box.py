import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext
from runtime_paths import DATA_DIR, FROZEN, PACKAGE_DIR
from PIL import Image, ImageTk
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from avatar_mapping import (
    ask_match_permission,
    download_box_images,
    resolve_unknown_styles,
    review_avatar_matches,
    unknown_prefixes,
)
from element_box import create_element_box_preview

BASE_DIR = DATA_DIR
APP_SETTINGS_FILE = BASE_DIR / "程序设置.json"
USER_DATA_DIR = BASE_DIR / "bilibili_user_data"
STATE_FILE = BASE_DIR / "bilibili_storage_state.json"
COOKIE_FILE = BASE_DIR / "bilibili_cookies.json"
DEBUG_DIR = BASE_DIR / "debug"
MAPPING_HISTORY_DIR = BASE_DIR / "映射表历史"
LOGIN_URL = "https://passport.bilibili.com/login"
HBR_URL = "https://game.bilibili.com/tool/hbr/"
NAV_API_URL = "https://api.bilibili.com/x/web-interface/nav"
BOX_URL = "https://ruriro.cc/hbr/StyleChart/"
MAPPING_FILE = BASE_DIR / "当前映射表.txt"
VIEWPORT = {"width": 1440, "height": 960}
DEFAULT_TIMEOUT_MS = 15000
PAGE_LOAD_TIMEOUT_MS = 30000
LOGIN_WAIT_TIMEOUT_SECONDS = 180
LOGIN_POLL_INTERVAL_SECONDS = 1.5
LOGIN_PAGE_IDLE_TIMEOUT_MS = 3000
HBR_PAGE_IDLE_TIMEOUT_MS = 5000
QR_SELECTOR_TIMEOUT_MS = 6000
HBR_SELECTOR_TIMEOUT_MS = 15000
HBR_SCROLL_WAIT_MS = 500
HBR_SCROLL_STEP_PX = 900
HBR_SCROLL_MAX_ROUNDS = 60
HBR_STABLE_ROUNDS = 5
HBR_PREPARE_RETRIES = 3
HBR_ARCHIVE_READY_TIMEOUT_MS = 15000
HBR_ARCHIVE_VIEW_ALL_TIMEOUT_MS = 15000
HBR_IDS_FILE = BASE_DIR / "b站ss_ssr_id列表.txt"
HBR_BREAK_DATA_FILE = BASE_DIR / "b站ss_ssr突破列表.txt"
HBR_ARCHIVE_READY_KEYWORDS = ["累计登录天数", "已解锁风格", "查看全部"]
HBR_ARCHIVE_VIEW_ALL_TEXT = "查看全部"
BOX_PAGE_IDLE_TIMEOUT_MS = 12000
BOX_GOTO_TIMEOUT_MS = 45000
BOX_GOTO_RETRY_COUNT = 1
BOX_GOTO_RETRY_WAIT_MS = 1500
BOX_READY_TIMEOUT_MS = 35000
BOX_DOMCONTENTLOADED_TIMEOUT_MS = 20000
BOX_REGION_SWITCH_TIMEOUT_MS = 40000
BOX_WRITE_APPLY_TIMEOUT_MS = 40000
BOX_INITIAL_SCREENSHOT_FILE = BASE_DIR / "box图初始状态.png"
BOX_OUTPUT_DIR = BASE_DIR
BOX_WRITE_DATA_FILE = BASE_DIR / "box写入数据.json"
BOX_READY_SELECTORS = [
    "canvas",
    "svg",
    "main",
    "body",
]
BOX_READY_KEYWORDS = [
    "StyleChart",
    "HBR",
    "BOX",
    "style",
]
BOX_REGION_OPTIONS = ("CN", "JP", "EN")
BOX_DOWNLOAD_ICON_PREFIX = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAALgAAAC4"
BOX_BUTTON_MIN_SIZE = 40
BOX_DOWNLOAD_TIMEOUT_MS = 30000
BOX_PREVIEW_MAX_SIZE = (1100, 720)
BOX_FALLBACK_SUFFIX = "_截图兜底"
MAPPING_HISTORY_PREFIX = "映射表_"
MAPPING_HISTORY_KEEP_COUNT = 5
QR_TAB_SELECTORS = [
    "text=扫码登录",
    "text=扫码登陆",
    "button:has-text('扫码登录')",
    "[role='tab']:has-text('扫码登录')",
    "[class*='tab']:has-text('扫码登录')",
]
QR_IMAGE_SELECTORS = [
    "[class*='qrcode'] canvas",
    "[class*='qr-code'] canvas",
    "[class*='qrCode'] canvas",
    "[class*='scan'] canvas",
    "[class*='qrcode'] img",
    "[class*='qr-code'] img",
    "[class*='qrCode'] img",
    "[class*='scan'] img",
    "img[src*='qrcode']",
    "canvas[width][height]",
]
QR_REFRESH_SELECTORS = [
    "text=刷新二维码",
    "text=点击刷新",
    "button:has-text('刷新二维码')",
    "button:has-text('点击刷新')",
    "[class*='refresh']",
]
QR_EXPIRED_KEYWORDS = [
    "二维码已失效",
    "二维码已过期",
    "请点击刷新",
    "点击刷新",
    "请重新扫码",
]
LOGIN_COOKIE_NAMES = {"SESSDATA", "DedeUserID"}
HBR_CARD_SELECTOR = '[class*="item"], [class*="icon"], [class*="card"]'
HBR_ARCHIVE_CARD_SELECTOR = '.card-box .style-item.card[data-id]'
HBR_SCROLL_CONTAINER_SELECTORS = [
    ".page.developing",
    ".page",
    ".van-tab__panel",
    ".van-tabs__content",
    ".van-swipe__track",
]
LOG_LISTENERS = []
APP_THEME = {
    "bg": "#0b0b0d",
    "surface": "#121216",
    "surface_alt": "#1b1b21",
    "panel": "#111115",
    "border": "#8f1f2f",
    "border_soft": "#5f1824",
    "text": "#f6f1f1",
    "muted": "#b5a8ad",
    "accent": "#d63b4c",
    "accent_dark": "#a61f31",
    "accent_soft": "#33141a",
    "success": "#52c48a",
    "success_soft": "#15251d",
    "warning": "#f0b24a",
    "warning_soft": "#2e2312",
    "danger": "#ff6b7c",
    "danger_soft": "#34141a",
    "log_bg": "#09090b",
    "log_text": "#f3edf0",
    "log_muted": "#9b8e94",
    "shadow": "#170b0e",
}

def configure_stdio():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            continue

def log(stage, message):
    text = f"[{stage}] {message}"
    print(text, flush=True)
    for listener in list(LOG_LISTENERS):
        try:
            listener(text)
        except Exception:
            continue

def load_show_browser():
    try:
        settings = json.loads(APP_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(settings, dict) and settings.get("show_browser") is True

def save_show_browser(enabled):
    temp_path = APP_SETTINGS_FILE.with_name(APP_SETTINGS_FILE.name + ".tmp")
    try:
        temp_path.write_text(
            json.dumps({"show_browser": bool(enabled)}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, APP_SETTINGS_FILE)
    finally:
        temp_path.unlink(missing_ok=True)

def browser_headless():
    return not load_show_browser()

def ensure_dirs():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    MAPPING_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

def save_debug_screenshot(page, stage):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = DEBUG_DIR / f"{stage}_{timestamp}.png"
    page.screenshot(path=str(path), full_page=True)
    log("调试截图", f"已保存: {path}")
    return path

def normalize_style_id(value):
    return str(value).strip()

def get_style_character_prefix(style_id):
    style_id = normalize_style_id(style_id)
    if len(style_id) < 3:
        raise RuntimeError(f"无效的风格 ID: {style_id}")
    return style_id[:-2]

def parse_mapping_value(mapping_value):
    mapping_value = mapping_value.strip()
    matched = re.match(r"^(.*-)(\d+)$", mapping_value)
    if not matched:
        raise RuntimeError(f"无法解析映射值: {mapping_value}")
    return matched.group(1), int(matched.group(2))

def initialize_mapping_table():
    mapping = {"1001103": "1:31a-1-1"}
    save_mapping_table(mapping)
    log("映射表", "映射表缺失或为空，已添加初始映射: 1001103: 1:31a-1-1")
    return mapping


def load_mapping_table():
    if not MAPPING_FILE.exists():
        bundled_mapping = PACKAGE_DIR / MAPPING_FILE.name
        if FROZEN and bundled_mapping.is_file():
            ensure_dirs()
            shutil.copyfile(bundled_mapping, MAPPING_FILE)
            log("映射表", f"已从安装包初始化映射表: {MAPPING_FILE}")
            return load_mapping_table()
        return initialize_mapping_table()
    mapping = {}
    has_content = False
    with MAPPING_FILE.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line:
                continue
            has_content = True
            idx = line.index(":") if ":" in line else -1
            if idx == -1:
                continue
            style_id = normalize_style_id(line[:idx])
            mapping_value = line[idx + 1 :].strip()
            if style_id and mapping_value:
                mapping[style_id] = mapping_value
    if not mapping:
        if has_content:
            raise RuntimeError("映射表格式无效。")
        return initialize_mapping_table()
    log("映射表", f"已读取 {len(mapping)} 条映射。")
    return mapping

def format_mapping_table(mapping):
    return "\n".join(
        f"{style_id}: {mapping_value}"
        for style_id, mapping_value in sorted(mapping.items(), key=lambda item: int(item[0]))
    )

def get_mapping_history_files():
    return sorted(
        MAPPING_HISTORY_DIR.glob(f"{MAPPING_HISTORY_PREFIX}*.txt"),
        key=lambda path: path.name,
    )

def hash_text(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def find_same_mapping_snapshot(content):
    content_hash = hash_text(content)
    matches = []
    for path in get_mapping_history_files():
        try:
            if hash_text(path.read_text(encoding="utf-8")) == content_hash:
                matches.append(path)
        except Exception:
            continue
    return matches

def make_mapping_history_path():
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    candidate = MAPPING_HISTORY_DIR / f"{MAPPING_HISTORY_PREFIX}{timestamp}.txt"
    index = 1
    while candidate.exists():
        candidate = MAPPING_HISTORY_DIR / f"{MAPPING_HISTORY_PREFIX}{timestamp}_{index}.txt"
        index += 1
    return candidate

def prune_mapping_history():
    files = sorted(get_mapping_history_files(), key=lambda path: path.name, reverse=True)
    for path in files[MAPPING_HISTORY_KEEP_COUNT:]:
        try:
            path.unlink()
            log("映射表", f"已清理旧映射表历史: {path.name}")
        except OSError:
            continue

def archive_mapping_snapshot(content):
    ensure_dirs()
    for path in find_same_mapping_snapshot(content):
        try:
            path.unlink()
            log("映射表", f"已删除重复的映射表历史: {path.name}")
        except OSError:
            continue
    history_path = make_mapping_history_path()
    history_path.write_text(content, encoding="utf-8")
    log("映射表", f"已归档映射表历史: {history_path.name}")
    prune_mapping_history()
    return history_path

def save_mapping_table(mapping):
    ensure_dirs()
    new_content = format_mapping_table(mapping)
    old_content = MAPPING_FILE.read_text(encoding="utf-8") if MAPPING_FILE.exists() else ""
    if old_content == new_content:
        log("映射表", "映射表无变化，已跳过保存与归档。")
        return False
    MAPPING_FILE.write_text(new_content, encoding="utf-8")
    archive_mapping_snapshot(new_content)
    log("映射表", f"映射表已更新: {MAPPING_FILE}")
    return True

def reconcile_mapping_table(mapping, all_style_ids, inferred_mapping=None, preserve_prefixes=()):
    inferred_mapping = inferred_mapping or {}
    occupied_keys = set(mapping.values())
    for style_id, box_key in inferred_mapping.items():
        if style_id in mapping or box_key in occupied_keys:
            raise RuntimeError(f"头像匹配与现有映射冲突: {style_id} -> {box_key}")
        occupied_keys.add(box_key)
    mapping = {**mapping, **inferred_mapping}
    normalized_ids = sorted(
        {normalize_style_id(style_id) for style_id in all_style_ids},
        key=int,
    )
    all_by_prefix = {}
    for style_id in normalized_ids:
        prefix = get_style_character_prefix(style_id)
        all_by_prefix.setdefault(prefix, []).append(style_id)
    mapping_by_prefix = {}
    for style_id, mapping_value in mapping.items():
        prefix = get_style_character_prefix(style_id)
        stem, slot_index = parse_mapping_value(mapping_value)
        group = mapping_by_prefix.setdefault(prefix, {"stem": stem, "ids": []})
        group["ids"].append((style_id, slot_index))
    updated_mapping = dict(mapping)
    changed = bool(inferred_mapping)
    unresolved_prefixes = []
    for prefix, ids in all_by_prefix.items():
        if prefix in preserve_prefixes:
            continue
        group = mapping_by_prefix.get(prefix)
        if not group:
            unresolved_prefixes.append(prefix)
            continue
        stem = group["stem"]
        sorted_ids = sorted(set(ids + [style_id for style_id, _ in group["ids"]]), key=int)
        rebuilt = {
            style_id: f"{stem}{index}"
            for index, style_id in enumerate(sorted_ids, start=1)
        }
        for style_id, mapping_value in rebuilt.items():
            if updated_mapping.get(style_id) != mapping_value:
                updated_mapping[style_id] = mapping_value
                changed = True
    if unresolved_prefixes:
        raise RuntimeError(
            "存在无法自动推断映射的新角色前缀: " + ", ".join(sorted(unresolved_prefixes))
        )
    if changed:
        save_mapping_table(updated_mapping)
    else:
        log("映射表", "映射表无需更新。")
    return updated_mapping

def build_box_write_data(mapping, break_rows):
    break_map = {
        normalize_style_id(row["id"]): int(row["breakNum"])
        for row in break_rows
    }
    write_data = {}
    match = 0
    miss = 0
    for style_id, storage_key in sorted(mapping.items(), key=lambda item: int(item[0])):
        if style_id in break_map:
            write_data[storage_key] = break_map[style_id]
            match += 1
        else:
            write_data[storage_key] = -1
            miss += 1
    BOX_WRITE_DATA_FILE.write_text(
        json.dumps(write_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log("BOX同步", f"已生成 BOX 写入数据，匹配 {match} 个，填充 -1 共 {miss} 个。")
    log("BOX同步", f"写入数据已保存到: {BOX_WRITE_DATA_FILE}")
    return write_data

def load_hbr_break_data_file():
    if not HBR_BREAK_DATA_FILE.exists():
        raise RuntimeError(f"未找到突破数据文件: {HBR_BREAK_DATA_FILE}")
    rows = []
    with HBR_BREAK_DATA_FILE.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            style_id, break_text = line.split(":", 1)
            style_id = normalize_style_id(style_id)
            break_text = break_text.strip()
            if not style_id or not break_text:
                continue
            rows.append({"id": style_id, "breakNum": int(break_text)})
    if not rows:
        raise RuntimeError("突破数据文件为空或格式无效。")
    log("BOX同步", f"已读取 {len(rows)} 条本地突破数据。")
    return rows

def load_box_write_data_file():
    if not BOX_WRITE_DATA_FILE.exists():
        raise RuntimeError(f"未找到 BOX 写入数据文件: {BOX_WRITE_DATA_FILE}")
    with BOX_WRITE_DATA_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict) or not data:
        raise RuntimeError("BOX 写入数据文件为空或格式无效。")
    normalized = {str(key): int(value) for key, value in data.items()}
    log("BOX同步", f"已读取 {len(normalized)} 条本地 BOX 写入数据。")
    return normalized

def run_mapping_update(hbr_result=None):
    mapping = load_mapping_table()
    if hbr_result is None:
        hbr_result = bilibili_login(update_bili_ids=True, update_break_data=False)
    all_ids = hbr_result.get("ids") or []
    if not all_ids:
        raise RuntimeError("未获取到 B站 SS/SSR 全量 ID，无法更新映射表。")
    unknown = unknown_prefixes(mapping, all_ids)
    additions = {}
    if unknown:
        if not ask_match_permission(unknown):
            log("头像匹配", "用户取消头像匹配；映射表未修改。")
            return None
        avatar_roles = hbr_result.get("avatar_roles") or {}
        if not avatar_roles:
            raise RuntimeError("未取得养成助手的圆形角色头像数据；映射表未保存。")
        log("头像匹配", "正在读取 BOX 卡片头像...")
        box_images = download_box_images(BOX_URL)
        review_items = {}
        additions = resolve_unknown_styles(
            mapping, all_ids, avatar_roles, box_images,
            on_skip=lambda style_id: log("头像匹配", f"已跳过角色 {style_id}，继续处理下一项。"),
            review_items=review_items,
        )
        if additions:
            approved = review_avatar_matches(review_items)
            if approved is None:
                log("头像匹配", "已取消最终复核，本轮新增映射未保存。")
                return None
            if any(additions.get(style_id) != value for style_id, value in approved.items()):
                raise RuntimeError("最终复核返回了不在本轮候选中的映射，未保存。")
            additions = approved
    return reconcile_mapping_table(mapping, all_ids, inferred_mapping=additions,
                                   preserve_prefixes=unknown)

def update_mapping_for_box_sync(hbr_result):
    try:
        updated = run_mapping_update(hbr_result=hbr_result)
    except Exception as exc:
        log("BOX同步", f"更新映射表失败，将继续使用现有映射表: {exc}")
        return load_mapping_table()
    if updated is None:
        log("BOX同步", "映射表未更新，继续使用现有映射表生成 BOX 图。")
        return load_mapping_table()
    return updated


def run_generate_box_write_data_from_files():
    mapping = load_mapping_table()
    break_rows = load_hbr_break_data_file()
    return build_box_write_data(mapping, break_rows)

def run_box_preview_from_saved_data():
    write_data = load_box_write_data_file()
    return run_box_preview_download(write_data=write_data)

def center_window(window, width, height):
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = max((screen_width - width) // 2, 0)
    y = max((screen_height - height) // 2, 0)
    window.geometry(f"{width}x{height}+{x}+{y}")

def count_nonempty_lines(path):
    file_path = Path(path)
    if not file_path.exists():
        return None
    with file_path.open("r", encoding="utf-8") as file:
        return sum(1 for line in file if line.strip())

class QRCodePopup:
    def __init__(self, image_path):
        self.image_path = Path(image_path)
        self.root = None
        self.closed = False
        self.image_label = None
        self.status_label = None
        self.tip_label = None
        self.photo = None

    def open(self):
        self.root = tk.Tk()
        self.root.title("B站扫码登录")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.root.configure(bg=APP_THEME["bg"])
        center_window(self.root, 420, 560)
        shell = tk.Frame(self.root, bg=APP_THEME["bg"], padx=24, pady=24)
        shell.pack(fill=tk.BOTH, expand=True)
        card = tk.Frame(
            shell,
            bg=APP_THEME["surface"],
            highlightthickness=1,
            highlightbackground=APP_THEME["border"],
            bd=0,
            padx=24,
            pady=24,
        )
        card.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            card,
            text="B站扫码登录",
            bg=APP_THEME["surface"],
            fg=APP_THEME["text"],
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card,
            text="请使用 B 站 App 扫描下方二维码，并在手机上确认登录。",
            bg=APP_THEME["surface"],
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 10),
            wraplength=320,
            justify="left",
        ).pack(anchor="w", pady=(6, 18))
        qr_frame = tk.Frame(
            card,
            bg=APP_THEME["surface_alt"],
            highlightthickness=1,
            highlightbackground=APP_THEME["border_soft"],
            padx=14,
            pady=14,
        )
        qr_frame.pack(fill=tk.X)
        self.photo = self._build_photo()
        self.image_label = tk.Label(qr_frame, image=self.photo, bg=APP_THEME["surface_alt"])
        self.image_label.image = self.photo
        self.image_label.pack()
        self.status_label = tk.Label(
            card,
            text="等待扫码",
            bg=APP_THEME["warning_soft"],
            fg=APP_THEME["warning"],
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=12,
            pady=6,
        )
        self.status_label.pack(anchor="w", pady=(18, 10))
        self.tip_label = tk.Label(
            card,
            text="如果二维码过期，程序会自动尝试刷新并更新当前窗口。",
            bg=APP_THEME["surface"],
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 9),
            wraplength=320,
            justify="left",
        )
        self.tip_label.pack(anchor="w")

    def _build_photo(self):
        resampling = getattr(Image, "Resampling", Image)
        image = Image.open(self.image_path)
        image = image.resize((280, 280), resampling.LANCZOS)
        return ImageTk.PhotoImage(image)

    def refresh_image(self):
        if self.root is None or self.closed or self.image_label is None:
            return
        self.photo = self._build_photo()
        self.image_label.configure(image=self.photo)
        self.image_label.image = self.photo

    def set_status(self, text, color="#666666"):
        if self.status_label is None or self.closed:
            return
        background = APP_THEME["surface_alt"]
        foreground = color
        if color == "#C62828":
            background = APP_THEME["danger_soft"]
            foreground = APP_THEME["danger"]
        elif color == "#666666":
            background = APP_THEME["warning_soft"]
            foreground = APP_THEME["warning"]
        self.status_label.configure(text=text, fg=foreground, bg=background)

    def process_events(self):
        if self.root is None or self.closed:
            return
        try:
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            self.closed = True
            self.root = None

    def close(self):
        if self.root is not None:
            try:
                self.root.destroy()
            except tk.TclError:
                pass
        self.root = None
        self.closed = True

    def _handle_close(self):
        self.close()

class BoxPreviewPopup:
    def __init__(self, image_path, element_path=None, element_error=None):
        self.image_path = Path(image_path)
        self.images = [("原版 BOX", self.image_path)]
        if element_path is not None:
            self.images.append(("属性 BOX", Path(element_path)))
        self.element_error = element_error
        self.current_index = 0
        self.root = None
        self.closed = False
        self.choice = None
        self.selected_dir = None
        self.image_label = None
        self.image_name_label = None
        self.status_label = None
        self.photo = None
        self.preview_max_size = BOX_PREVIEW_MAX_SIZE

    def open(self):
        self.root = tk.Tk()
        self.root.title("BOX 图预览")
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.root.bind("<Left>", lambda event: self._change_image(-1))
        self.root.bind("<Right>", lambda event: self._change_image(1))
        self.root.configure(bg=APP_THEME["bg"])
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = min(1220, max(760, screen_width - 120))
        window_height = min(900, max(640, screen_height - 120))
        self.root.minsize(min(window_width, 880), min(window_height, 720))
        center_window(self.root, window_width, window_height)
        self.preview_max_size = (
            max(520, window_width - 160),
            max(320, window_height - 310),
        )
        shell = tk.Frame(self.root, bg=APP_THEME["bg"], padx=24, pady=24)
        shell.pack(fill=tk.BOTH, expand=True)
        header = tk.Frame(shell, bg=APP_THEME["bg"])
        header.pack(fill=tk.X, pady=(0, 14))
        title = tk.Label(
            header,
            text="BOX 图预览",
            font=("Microsoft YaHei UI", 12, "bold"),
            bg=APP_THEME["bg"],
            fg=APP_THEME["text"],
        )
        title.pack(anchor="w")
        subtitle = tk.Label(
            header,
            text="先确认预览效果，再选择下载位置。关闭窗口则放弃本次导出。",
            bg=APP_THEME["bg"],
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 10),
        )
        subtitle.pack(anchor="w", pady=(6, 0))
        footer = tk.Frame(shell, bg=APP_THEME["bg"])
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(14, 0))
        preview_card = tk.Frame(
            shell,
            bg=APP_THEME["surface"],
            highlightthickness=1,
            highlightbackground=APP_THEME["border"],
            bd=0,
            padx=18,
            pady=18,
        )
        preview_card.pack(fill=tk.BOTH, expand=True)
        navigation = tk.Frame(preview_card, bg=APP_THEME["surface"])
        navigation.pack(fill=tk.X, pady=(0, 10))
        tk.Button(
            navigation, text="←", width=5, command=lambda: self._change_image(-1),
            state=tk.NORMAL if len(self.images) > 1 else tk.DISABLED,
            bg=APP_THEME["surface_alt"], fg=APP_THEME["text"],
            activebackground=APP_THEME["border"], activeforeground=APP_THEME["text"],
            relief=tk.FLAT, bd=0, font=("Segoe UI Symbol", 12),
        ).pack(side=tk.LEFT)
        self.image_name_label = tk.Label(
            navigation, text=self._current_image_title(), bg=APP_THEME["surface"],
            fg=APP_THEME["text"], font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.image_name_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(
            navigation, text="→", width=5, command=lambda: self._change_image(1),
            state=tk.NORMAL if len(self.images) > 1 else tk.DISABLED,
            bg=APP_THEME["surface_alt"], fg=APP_THEME["text"],
            activebackground=APP_THEME["border"], activeforeground=APP_THEME["text"],
            relief=tk.FLAT, bd=0, font=("Segoe UI Symbol", 12),
        ).pack(side=tk.RIGHT)
        self.photo = self._build_photo()
        self.image_label = tk.Label(preview_card, image=self.photo, bd=0, bg=APP_THEME["surface"])
        self.image_label.image = self.photo
        self.image_label.pack(fill=tk.BOTH, expand=True)
        button_frame = tk.Frame(footer, bg=APP_THEME["bg"])
        button_frame.pack(anchor="w")
        choices = [("下载原版 BOX", "original")]
        if len(self.images) > 1:
            choices.extend((("下载属性 BOX", "element"), ("下载两张", "both")))
        for label, selection in choices:
            tk.Button(
                button_frame,
                text=label,
                width=16,
                font=("Microsoft YaHei UI", 10),
                bg=APP_THEME["accent"],
                fg="#ffffff",
                activebackground=APP_THEME["accent_dark"],
                activeforeground="#ffffff",
                relief=tk.FLAT,
                bd=0,
                padx=14,
                pady=8,
                command=lambda choice=selection: self._download_with_picker(choice),
            ).pack(side=tk.LEFT, padx=8)
        tk.Button(
            button_frame,
            text="关闭窗口",
            width=16,
            font=("Microsoft YaHei UI", 10),
            bg=APP_THEME["surface"],
            fg=APP_THEME["text"],
            activebackground=APP_THEME["surface_alt"],
            activeforeground=APP_THEME["text"],
            relief=tk.FLAT,
            bd=0,
            padx=14,
            pady=8,
            command=self._handle_close,
        ).pack(side=tk.LEFT, padx=8)
        self.status_label = tk.Label(
            footer,
            text=(f"属性 BOX 图生成失败：{self.element_error}" if self.element_error else
                  "关闭窗口等价于放弃本次下载，临时预览图会自动删除。"),
            font=("Microsoft YaHei UI", 9),
            fg=APP_THEME["muted"],
            bg=APP_THEME["bg"],
            wraplength=max(520, window_width - 100),
        )
        self.status_label.pack(anchor="w", pady=(10, 0))

    def _build_photo(self):
        resampling = getattr(Image, "Resampling", Image)
        with Image.open(self.images[self.current_index][1]) as image:
            preview = image.copy()
        preview.thumbnail(self.preview_max_size, resampling.LANCZOS)
        return ImageTk.PhotoImage(preview)

    def _current_image_title(self):
        return f"{self.images[self.current_index][0]}  {self.current_index + 1}/{len(self.images)}"

    def _change_image(self, direction):
        if len(self.images) < 2 or self.closed:
            return
        self.current_index = (self.current_index + direction) % len(self.images)
        self.photo = self._build_photo()
        self.image_label.configure(image=self.photo)
        self.image_label.image = self.photo
        self.image_name_label.configure(text=self._current_image_title())

    def set_status(self, text, color="#666666"):
        if self.status_label is None or self.closed:
            return
        self.status_label.configure(text=text, fg=color)

    def process_events(self):
        if self.root is None or self.closed:
            return
        try:
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            self.closed = True
            self.root = None

    def wait_for_choice(self):
        while not self.closed and self.choice is None:
            self.process_events()
            time.sleep(0.05)
        return self.choice, self.selected_dir

    def close(self):
        if self.root is not None:
            try:
                self.root.destroy()
            except tk.TclError:
                pass
        self.root = None
        self.closed = True

    def _download_with_picker(self, selection="original"):
        directory = filedialog.askdirectory(title="选择 BOX 图保存位置")
        if not directory:
            self.set_status("未选择保存位置，本次不会开始下载。", "#666666")
            return
        self.selected_dir = Path(directory)
        self.choice = selection
        self.close()

    def _handle_close(self):
        self.choice = "close"
        self.close()

def open_path_with_system(path):
    target = Path(path)
    if not target.exists():
        raise RuntimeError(f"目标不存在: {target}")
    try:
        os.startfile(str(target))
    except AttributeError:
        subprocess.Popen(["explorer", str(target)])

def remove_path(path):
    target = Path(path)
    if not target.exists():
        return False
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return True

def clear_login_state():
    removed = []
    for path in [USER_DATA_DIR, STATE_FILE, COOKIE_FILE]:
        if remove_path(path):
            removed.append(path.name)
    if removed:
        log("登录态", f"已清理登录态文件: {', '.join(removed)}")
    else:
        log("登录态", "未发现可清理的登录态文件。")
    return removed

def build_self_command(extra_args):
    if FROZEN:
        return [sys.executable, *extra_args]
    return [sys.executable, "-X", "utf8", "-u", str(Path(__file__).resolve()), *extra_args]

def get_hidden_subprocess_kwargs():
    kwargs = {}
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["creationflags"] = creationflags
        kwargs["startupinfo"] = startupinfo
    return kwargs

def terminate_process_tree(process):
    if process is None:
        return True
    try:
        if process.poll() is not None:
            return True
    except Exception:
        return True
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                **get_hidden_subprocess_kwargs(),
            )
        else:
            process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
    finally:
        try:
            if process.stdout:
                process.stdout.close()
        except Exception:
            pass
    return process.poll() is not None

class MainApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("炽焰天穹 BOX 工具")
        self.root.minsize(980, 760)
        self.root.protocol("WM_DELETE_WINDOW", self.handle_close)
        self.root.configure(bg=APP_THEME["bg"])
        center_window(self.root, 1120, 860)
        self.advanced_visible = False
        self.current_process = None
        self.stdout_thread = None
        self.output_queue = []
        self.queue_lock = threading.Lock()
        self.action_buttons = []
        self.summary_labels = {}
        self.runtime_badge = None
        self.runtime_text = None
        self.status_label = None
        self.log_text = None
        self.log_panel = None
        self.log_visible = False
        self.log_toggle_button = None
        self.log_history = []
        self.log_window = None
        self.log_window_text = None
        self.advanced_window = None
        self.mapping_history_window = None
        self.mapping_history_listbox = None
        self.mapping_history_preview = None
        self.mapping_history_files = []
        self.show_browser_var = tk.BooleanVar(master=self.root, value=load_show_browser())
        self._build_ui()
        self.refresh_summary_cards()
        self.set_runtime_state("idle", "等待操作")
        self.root.after(120, self.poll_process_output)

    def _build_ui(self):
        container = tk.Frame(self.root, bg=APP_THEME["bg"], padx=24, pady=22)
        container.pack(fill=tk.BOTH, expand=True)
        self._build_header(container)
        self._build_summary_cards(container)
        self._build_primary_actions(container)
        self._build_mapping_strip(container)
        self._build_advanced_panel(container)
        self._build_log_panel(container)
        self.append_log("主界面", "工具已就绪。")

    def _build_header(self, parent):
        header = tk.Frame(
            parent,
            bg=APP_THEME["surface"],
            highlightthickness=1,
            highlightbackground=APP_THEME["border"],
            bd=0,
            padx=22,
            pady=20,
        )
        header.pack(fill=tk.X)
        left = tk.Frame(header, bg=APP_THEME["surface"])
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(
            left,
            text="炽焰天穹 BOX 工具",
            bg=APP_THEME["surface"],
            fg=APP_THEME["text"],
            font=("Microsoft YaHei UI", 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            left,
            text="抓取 B 站 HBR 数据、维护映射表，并生成可预览的 BOX 图。",
            bg=APP_THEME["surface"],
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(8, 0))
        right = tk.Frame(header, bg=APP_THEME["surface"])
        right.pack(side=tk.RIGHT, anchor="n")
        self.runtime_badge = tk.Label(
            right,
            text="空闲",
            bg=APP_THEME["surface_alt"],
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=14,
            pady=7,
        )
        self.runtime_badge.pack(anchor="e")
        self.runtime_text = tk.Label(
            right,
            text="等待操作",
            bg=APP_THEME["surface"],
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 9),
            justify="right",
        )
        self.runtime_text.pack(anchor="e", pady=(10, 0))

    def _build_summary_cards(self, parent):
        section = tk.Frame(parent, bg=APP_THEME["bg"])
        section.pack(fill=tk.X, pady=(16, 0))
        for column in range(4):
            section.grid_columnconfigure(column, weight=1)
        cards = [
            ("mapping", "映射表", "当前启用的映射条目"),
            ("ids", "全量 ID", "SS/SSR 总表"),
            ("break", "突破数据", "玩家持有风格"),
            ("box", "BOX 写入", "预览与同步数据"),
        ]
        for index, (key, title, hint) in enumerate(cards):
            card = tk.Frame(
                section,
                bg=APP_THEME["surface"],
                highlightthickness=1,
                highlightbackground=APP_THEME["border_soft"],
                bd=0,
                padx=16,
                pady=14,
            )
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 10) if index < 3 else 0)
            tk.Label(
                card,
                text=title,
                bg=APP_THEME["surface"],
                fg=APP_THEME["muted"],
                font=("Microsoft YaHei UI", 9),
            ).pack(anchor="w")
            value_label = tk.Label(
                card,
                text="未生成",
                bg=APP_THEME["surface"],
                fg=APP_THEME["text"],
                font=("Microsoft YaHei UI", 16, "bold"),
            )
            value_label.pack(anchor="w", pady=(10, 4))
            hint_label = tk.Label(
                card,
                text=hint,
                bg=APP_THEME["surface"],
                fg=APP_THEME["muted"],
                font=("Microsoft YaHei UI", 9),
            )
            hint_label.pack(anchor="w")
            self.summary_labels[key] = {
                "value": value_label,
                "hint": hint_label,
            }

    def _build_primary_actions(self, parent):
        section = tk.Frame(parent, bg=APP_THEME["bg"])
        section.pack(fill=tk.X, pady=(18, 0))
        section.grid_columnconfigure(0, weight=1)
        section.grid_columnconfigure(1, weight=1)
        self._create_action_card(
            section,
            0,
            0,
            "一键同步 BOX",
            "自动完成登录、抓取全量 ID 与突破数据，更新映射表后生成 BOX 图并进入预览导出。",
            "适合日常同步；发现新角色时会弹出头像匹配确认",
            "立即开始",
            lambda: self.start_subprocess(["--sync-box"], "一键同步 BOX"),
            accent=True,
        )
        self._create_action_card(
            section,
            0,
            1,
            "预览 BOX 图",
            "直接读取本地 box写入数据，快速查看当前成图效果。",
            "不会重新抓取 B 站",
            "打开预览",
            self.preview_box_from_json,
            accent=True,
        )

    def _build_mapping_strip(self, parent):
        strip = tk.Frame(
            parent,
            bg=APP_THEME["surface"],
            highlightthickness=1,
            highlightbackground=APP_THEME["border"],
            bd=0,
            padx=18,
            pady=16,
        )
        strip.pack(fill=tk.X, pady=(16, 0))
        text_area = tk.Frame(strip, bg=APP_THEME["surface"])
        text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(
            text_area,
            text="更新映射表",
            bg=APP_THEME["surface"],
            fg=APP_THEME["text"],
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            text_area,
            text="更新 SS/SSR 映射；遇到未知前缀时可选择用圆形头像查找 BOX 对应项。",
            bg=APP_THEME["surface"],
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(6, 0))
        button = tk.Button(
            strip,
            text="更新映射表",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=APP_THEME["surface"],
            fg=APP_THEME["accent"],
            activebackground=APP_THEME["accent_soft"],
            activeforeground=APP_THEME["accent_dark"],
            relief=tk.FLAT,
            bd=0,
            padx=18,
            pady=10,
            command=lambda: self.start_subprocess(["--update-mapping"], "更新映射表"),
        )
        button.pack(side=tk.RIGHT)
        self.action_buttons.append(button)

    def _build_advanced_panel(self, parent):
        self.advanced_toggle_button = tk.Button(
            parent,
            text="打开高级功能",
            font=("Microsoft YaHei UI", 10),
            bg=APP_THEME["bg"],
            fg=APP_THEME["accent"],
            activebackground=APP_THEME["bg"],
            activeforeground=APP_THEME["accent_dark"],
            relief=tk.FLAT,
            bd=0,
            padx=2,
            pady=10,
            command=self.open_advanced_window,
            anchor="w",
        )
        self.advanced_toggle_button.pack(fill=tk.X, pady=(8, 0))

    def _build_log_panel(self, parent):
        panel = tk.Frame(
            parent,
            bg=APP_THEME["surface"],
            highlightthickness=1,
            highlightbackground=APP_THEME["border"],
            bd=0,
            padx=18,
            pady=18,
        )
        panel.pack(fill=tk.X, pady=(18, 0))
        header = tk.Frame(panel, bg=APP_THEME["surface"])
        header.pack(fill=tk.X)
        left = tk.Frame(header, bg=APP_THEME["surface"])
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            left,
            text="运行动态",
            bg=APP_THEME["surface"],
            fg=APP_THEME["text"],
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(anchor="w")
        self.status_label = tk.Label(
            left,
            text="等待操作",
            bg=APP_THEME["surface"],
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 9),
            justify="left",
        )
        self.status_label.pack(anchor="w", pady=(6, 0))
        toolbar = tk.Frame(header, bg=APP_THEME["surface"])
        toolbar.pack(side=tk.RIGHT)
        open_button = tk.Button(
            toolbar,
            text="打开运行动态",
            font=("Microsoft YaHei UI", 9),
            bg=APP_THEME["surface_alt"],
            fg=APP_THEME["text"],
            activebackground=APP_THEME["accent_soft"],
            activeforeground=APP_THEME["accent_dark"],
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=8,
            command=self.open_log_window,
        )
        open_button.pack(side=tk.LEFT, padx=(0, 8))
        clear_button = tk.Button(
            toolbar,
            text="清空日志",
            font=("Microsoft YaHei UI", 9),
            bg=APP_THEME["surface_alt"],
            fg=APP_THEME["text"],
            activebackground=APP_THEME["accent_soft"],
            activeforeground=APP_THEME["accent_dark"],
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=8,
            command=self.clear_log,
        )
        clear_button.pack(side=tk.LEFT)
        self.action_buttons.append(clear_button)

    def _create_action_card(self, parent, row, column, title, desc, hint, button_text, command, accent=False):
        bg = APP_THEME["surface"]
        border = APP_THEME["accent"] if accent else APP_THEME["border_soft"]
        button_bg = APP_THEME["accent"] if accent else APP_THEME["surface_alt"]
        button_fg = "#ffffff" if accent else APP_THEME["text"]
        active_bg = APP_THEME["accent_dark"] if accent else APP_THEME["accent_soft"]
        active_fg = "#ffffff" if accent else APP_THEME["accent_dark"]
        card = tk.Frame(
            parent,
            bg=bg,
            highlightthickness=1,
            highlightbackground=border,
            bd=0,
            padx=18,
            pady=18,
        )
        card.grid(row=row, column=column, sticky="nsew", padx=(0, 10) if column == 0 else (10, 0))
        tk.Label(
            card,
            text=title,
            bg=bg,
            fg=APP_THEME["text"],
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card,
            text=desc,
            bg=bg,
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 10),
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(10, 8))
        tk.Label(
            card,
            text=hint,
            bg=bg,
            fg=APP_THEME["accent"] if accent else APP_THEME["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(0, 16))
        button = tk.Button(
            card,
            text=button_text,
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=button_bg,
            fg=button_fg,
            activebackground=active_bg,
            activeforeground=active_fg,
            relief=tk.FLAT,
            bd=0,
            padx=16,
            pady=10,
            command=command,
        )
        button.pack(anchor="w")
        self.action_buttons.append(button)

    def refresh_summary_cards(self):
        mapping_count = count_nonempty_lines(MAPPING_FILE)
        history_count = len(get_mapping_history_files())
        ids_count = count_nonempty_lines(HBR_IDS_FILE)
        break_count = count_nonempty_lines(HBR_BREAK_DATA_FILE)
        box_count = None
        if BOX_WRITE_DATA_FILE.exists():
            try:
                box_count = len(load_box_write_data_file())
            except Exception:
                box_count = None
        login_ready = USER_DATA_DIR.exists() and any(USER_DATA_DIR.iterdir())
        self._set_summary_card("mapping", f"{mapping_count or 0} 条", f"历史 {history_count} 份")
        self._set_summary_card("ids", f"{ids_count} 条" if ids_count is not None else "未生成", "SS/SSR 全量风格")
        self._set_summary_card("break", f"{break_count} 条" if break_count is not None else "未生成", "玩家当前图鉴")
        self._set_summary_card("box", f"{box_count} 条" if box_count is not None else "未生成", "登录态已缓存" if login_ready else "下次需扫码登录")

    def _set_summary_card(self, key, value, hint):
        labels = self.summary_labels.get(key)
        if not labels:
            return
        labels["value"].configure(text=value)
        labels["hint"].configure(text=hint)

    def _configure_log_tags(self, widget):
        widget.tag_configure("timestamp", foreground=APP_THEME["log_muted"])
        widget.tag_configure("default", foreground=APP_THEME["log_text"])
        widget.tag_configure("主界面", foreground="#ffd48d")
        widget.tag_configure("流程", foreground="#c7d2fe")
        widget.tag_configure("错误", foreground="#ff9c92")
        widget.tag_configure("调试截图", foreground="#9dd8ff")
        widget.tag_configure("映射表", foreground="#ffda95")
        widget.tag_configure("BOX页面", foreground="#9ee6d7")
        widget.tag_configure("BOX同步", foreground="#c8f2a8")
        widget.tag_configure("HBR更新", foreground="#f8c3ff")
        widget.tag_configure("HBR突破", foreground="#f6c08b")
        widget.tag_configure("登录态", foreground="#8fd0ff")

    def open_advanced_window(self):
        if self.advanced_window is not None and self.advanced_window.winfo_exists():
            self.advanced_window.lift()
            self.advanced_window.focus_force()
            return
        window = tk.Toplevel(self.root)
        self.advanced_window = window
        window.title("高级功能")
        window.configure(bg=APP_THEME["bg"])
        window.minsize(820, 620)
        center_window(window, 900, 680)
        window.protocol("WM_DELETE_WINDOW", self.close_advanced_window)
        shell = tk.Frame(window, bg=APP_THEME["bg"], padx=20, pady=20)
        shell.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            shell,
            text="高级功能",
            bg=APP_THEME["bg"],
            fg=APP_THEME["text"],
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            shell,
            text="这里放置日常不需要频繁点击，但对排查和手动维护很有用的操作。",
            bg=APP_THEME["bg"],
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(6, 14))
        browser_checkbox = tk.Checkbutton(
            shell,
            text="运行时显示浏览器窗口",
            variable=self.show_browser_var,
            command=self.on_browser_visibility_changed,
            bg=APP_THEME["bg"],
            fg=APP_THEME["text"],
            selectcolor=APP_THEME["surface"],
            activebackground=APP_THEME["bg"],
            activeforeground=APP_THEME["text"],
            font=("Microsoft YaHei UI", 10),
        )
        browser_checkbox.pack(anchor="w")
        self.action_buttons.append(browser_checkbox)
        tk.Label(
            shell,
            text="开启后，后续任务会显示 B 站、原版 BOX 和属性 BOX 的自动化浏览器窗口。",
            bg=APP_THEME["bg"],
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(2, 12))
        content = tk.Frame(shell, bg=APP_THEME["bg"])
        content.pack(fill=tk.BOTH, expand=True)
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)
        tools = [
            ("打开映射表", "快速编辑当前生效的映射文件。", self.open_mapping_file),
            ("使用历史映射表", "从历史版本中挑选一个，恢复为当前映射表。", self.open_mapping_history_window),
            ("打开输出目录", "查看导出的图片、日志和数据文件。", self.open_output_dir),
            ("更新全量 ID", "只抓取最新 SS/SSR 总表。", lambda: self.start_subprocess(["--update-bili-ids"], "更新全量 ID")),
            ("抓取突破数据", "只刷新玩家当前突破列表。", lambda: self.start_subprocess(["--update-break-data"], "抓取突破数据")),
            ("生成 BOX 写入数据", "使用本地映射和突破数据生成 JSON。", lambda: self.start_subprocess(["--generate-box-write-data"], "生成 BOX 写入数据")),
            ("BOX 初始截图", "仅打开 BOX 页面并截取初始状态。", lambda: self.start_subprocess(["--box-initial-shot"], "BOX 初始截图")),
            ("退出登录", "清除本地登录态，下次运行时重新扫码登录。", self.confirm_clear_login_state),
        ]
        for index, (title, desc, command) in enumerate(tools):
            row = index // 2
            column = index % 2
            card = tk.Frame(
                content,
                bg=APP_THEME["surface"],
                highlightthickness=1,
                highlightbackground=APP_THEME["border_soft"],
                bd=0,
                padx=14,
                pady=12,
            )
            card.grid(row=row, column=column, sticky="nsew", padx=6, pady=6)
            tk.Label(
                card,
                text=title,
                bg=APP_THEME["surface"],
                fg=APP_THEME["text"],
                font=("Microsoft YaHei UI", 10, "bold"),
            ).pack(anchor="w")
            tk.Label(
                card,
                text=desc,
                bg=APP_THEME["surface"],
                fg=APP_THEME["muted"],
                font=("Microsoft YaHei UI", 9),
                wraplength=320,
                justify="left",
            ).pack(anchor="w", pady=(6, 12))
            button = tk.Button(
                card,
                text=title,
                font=("Microsoft YaHei UI", 9),
                bg=APP_THEME["surface_alt"],
                fg=APP_THEME["text"],
                activebackground=APP_THEME["accent_soft"],
                activeforeground=APP_THEME["accent_dark"],
                relief=tk.FLAT,
                bd=0,
                padx=12,
                pady=8,
                command=command,
            )
            button.pack(anchor="w")

    def on_browser_visibility_changed(self):
        enabled = self.show_browser_var.get()
        try:
            save_show_browser(enabled)
        except OSError as exc:
            self.show_browser_var.set(load_show_browser())
            messagebox.showerror("保存设置失败", str(exc), parent=self.advanced_window or self.root)
            return
        self.append_log("主界面", "后续任务将显示浏览器窗口。" if enabled else "后续任务将隐藏浏览器窗口。")

    def close_advanced_window(self):
        if self.advanced_window is not None and self.advanced_window.winfo_exists():
            self.advanced_window.destroy()
        self.advanced_window = None

    def open_mapping_history_window(self):
        history_files = sorted(get_mapping_history_files(), key=lambda path: path.name, reverse=True)
        if not history_files:
            messagebox.showinfo("没有历史映射表", "当前还没有可用的历史映射表。", parent=self.root)
            return
        if self.mapping_history_window is not None and self.mapping_history_window.winfo_exists():
            self.mapping_history_files = history_files
            self.refresh_mapping_history_list()
            self.mapping_history_window.lift()
            self.mapping_history_window.focus_force()
            return
        window = tk.Toplevel(self.root)
        self.mapping_history_window = window
        self.mapping_history_files = history_files
        window.title("使用历史映射表")
        window.configure(bg=APP_THEME["bg"])
        window.minsize(920, 620)
        center_window(window, 980, 700)
        window.protocol("WM_DELETE_WINDOW", self.close_mapping_history_window)
        shell = tk.Frame(window, bg=APP_THEME["bg"], padx=20, pady=20)
        shell.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            shell,
            text="使用历史映射表",
            bg=APP_THEME["bg"],
            fg=APP_THEME["text"],
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            shell,
            text="左侧选择历史版本，右侧查看内容预览。确认后可直接恢复为当前映射表。",
            bg=APP_THEME["bg"],
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(6, 14))
        content = tk.Frame(shell, bg=APP_THEME["bg"])
        content.pack(fill=tk.BOTH, expand=True)
        content.grid_columnconfigure(0, weight=0)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)
        left_card = tk.Frame(
            content,
            bg=APP_THEME["surface"],
            highlightthickness=1,
            highlightbackground=APP_THEME["border_soft"],
            bd=0,
            padx=12,
            pady=12,
        )
        left_card.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        tk.Label(
            left_card,
            text="历史版本",
            bg=APP_THEME["surface"],
            fg=APP_THEME["text"],
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 8))
        listbox = tk.Listbox(
            left_card,
            width=30,
            height=22,
            bg=APP_THEME["surface_alt"],
            fg=APP_THEME["text"],
            selectbackground=APP_THEME["accent"],
            selectforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            activestyle="none",
            font=("Consolas", 10),
        )
        listbox.pack(fill=tk.BOTH, expand=True)
        listbox.bind("<<ListboxSelect>>", lambda event: self.refresh_mapping_history_preview())
        self.mapping_history_listbox = listbox
        right_card = tk.Frame(
            content,
            bg=APP_THEME["surface"],
            highlightthickness=1,
            highlightbackground=APP_THEME["border_soft"],
            bd=0,
            padx=12,
            pady=12,
        )
        right_card.grid(row=0, column=1, sticky="nsew")
        right_card.grid_rowconfigure(1, weight=1)
        right_card.grid_columnconfigure(0, weight=1)
        tk.Label(
            right_card,
            text="内容预览",
            bg=APP_THEME["surface"],
            fg=APP_THEME["text"],
            font=("Microsoft YaHei UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        preview = scrolledtext.ScrolledText(
            right_card,
            wrap="none",
            font=("Consolas", 10),
            bg=APP_THEME["log_bg"],
            fg=APP_THEME["log_text"],
            insertbackground=APP_THEME["log_text"],
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=12,
            state="disabled",
        )
        preview.grid(row=1, column=0, sticky="nsew")
        self.mapping_history_preview = preview
        footer = tk.Frame(shell, bg=APP_THEME["bg"])
        footer.pack(fill=tk.X, pady=(14, 0))
        tk.Button(
            footer,
            text="使用所选版本",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=APP_THEME["accent"],
            fg="#ffffff",
            activebackground=APP_THEME["accent_dark"],
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=16,
            pady=10,
            command=self.apply_selected_mapping_history,
        ).pack(side=tk.LEFT)
        tk.Button(
            footer,
            text="打开历史目录",
            font=("Microsoft YaHei UI", 10),
            bg=APP_THEME["surface_alt"],
            fg=APP_THEME["text"],
            activebackground=APP_THEME["accent_soft"],
            activeforeground=APP_THEME["accent_dark"],
            relief=tk.FLAT,
            bd=0,
            padx=16,
            pady=10,
            command=lambda: open_path_with_system(MAPPING_HISTORY_DIR),
        ).pack(side=tk.LEFT, padx=(10, 0))
        tk.Button(
            footer,
            text="关闭窗口",
            font=("Microsoft YaHei UI", 10),
            bg=APP_THEME["surface_alt"],
            fg=APP_THEME["text"],
            activebackground=APP_THEME["accent_soft"],
            activeforeground=APP_THEME["accent_dark"],
            relief=tk.FLAT,
            bd=0,
            padx=16,
            pady=10,
            command=self.close_mapping_history_window,
        ).pack(side=tk.RIGHT)
        self.refresh_mapping_history_list()

    def close_mapping_history_window(self):
        if self.mapping_history_window is not None and self.mapping_history_window.winfo_exists():
            self.mapping_history_window.destroy()
        self.mapping_history_window = None
        self.mapping_history_listbox = None
        self.mapping_history_preview = None
        self.mapping_history_files = []

    def refresh_mapping_history_list(self):
        if self.mapping_history_listbox is None:
            return
        self.mapping_history_listbox.delete(0, tk.END)
        for path in self.mapping_history_files:
            self.mapping_history_listbox.insert(tk.END, path.name)
        if self.mapping_history_files:
            self.mapping_history_listbox.selection_set(0)
            self.mapping_history_listbox.activate(0)
            self.refresh_mapping_history_preview()

    def refresh_mapping_history_preview(self):
        if self.mapping_history_listbox is None or self.mapping_history_preview is None:
            return
        selection = self.mapping_history_listbox.curselection()
        if not selection:
            return
        path = self.mapping_history_files[selection[0]]
        content = path.read_text(encoding="utf-8")
        self.mapping_history_preview.configure(state="normal")
        self.mapping_history_preview.delete("1.0", tk.END)
        self.mapping_history_preview.insert(tk.END, content)
        self.mapping_history_preview.configure(state="disabled")

    def apply_selected_mapping_history(self):
        if self.mapping_history_listbox is None:
            return
        selection = self.mapping_history_listbox.curselection()
        if not selection:
            messagebox.showwarning("未选择版本", "请先选择一个历史映射表版本。", parent=self.mapping_history_window or self.root)
            return
        history_path = self.mapping_history_files[selection[0]]
        confirmed = messagebox.askyesno(
            "确认恢复",
            f"确定要将 {history_path.name} 恢复为当前映射表吗？",
            parent=self.mapping_history_window or self.root,
        )
        if not confirmed:
            return
        new_content = history_path.read_text(encoding="utf-8")
        old_content = MAPPING_FILE.read_text(encoding="utf-8") if MAPPING_FILE.exists() else ""
        if old_content == new_content:
            messagebox.showinfo("无需恢复", "当前映射表与所选历史版本一致。", parent=self.mapping_history_window or self.root)
            return
        if old_content.strip():
            archive_mapping_snapshot(old_content)
        MAPPING_FILE.write_text(new_content, encoding="utf-8")
        archive_mapping_snapshot(new_content)
        self.refresh_summary_cards()
        self.append_log("映射表", f"已恢复历史映射表版本: {history_path.name}")
        messagebox.showinfo("恢复完成", f"已将 {history_path.name} 恢复为当前映射表。", parent=self.mapping_history_window or self.root)
        self.mapping_history_files = sorted(get_mapping_history_files(), key=lambda path: path.name, reverse=True)
        self.refresh_mapping_history_list()

    def open_log_window(self):
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.lift()
            self.log_window.focus_force()
            return
        window = tk.Toplevel(self.root)
        self.log_window = window
        window.title("运行动态")
        window.configure(bg=APP_THEME["bg"])
        window.minsize(900, 620)
        center_window(window, 980, 720)
        window.protocol("WM_DELETE_WINDOW", self.close_log_window)
        shell = tk.Frame(window, bg=APP_THEME["bg"], padx=20, pady=20)
        shell.pack(fill=tk.BOTH, expand=True)
        header = tk.Frame(shell, bg=APP_THEME["bg"])
        header.pack(fill=tk.X, pady=(0, 12))
        text_area = tk.Frame(header, bg=APP_THEME["bg"])
        text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(
            text_area,
            text="运行动态",
            bg=APP_THEME["bg"],
            fg=APP_THEME["text"],
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            text_area,
            text="这里会实时显示当前任务的运行日志，方便你手动查看和排查问题。",
            bg=APP_THEME["bg"],
            fg=APP_THEME["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(6, 0))
        toolbar = tk.Frame(header, bg=APP_THEME["bg"])
        toolbar.pack(side=tk.RIGHT)
        tk.Button(
            toolbar,
            text="清空日志",
            font=("Microsoft YaHei UI", 9),
            bg=APP_THEME["surface_alt"],
            fg=APP_THEME["text"],
            activebackground=APP_THEME["accent_soft"],
            activeforeground=APP_THEME["accent_dark"],
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=8,
            command=self.clear_log,
        ).pack(side=tk.LEFT)
        text_widget = scrolledtext.ScrolledText(
            shell,
            wrap="word",
            font=("Consolas", 10),
            bg=APP_THEME["log_bg"],
            fg=APP_THEME["log_text"],
            insertbackground=APP_THEME["log_text"],
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=12,
            state="disabled",
        )
        text_widget.pack(fill=tk.BOTH, expand=True)
        self._configure_log_tags(text_widget)
        self.log_window_text = text_widget
        self.sync_log_window()

    def close_log_window(self):
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.destroy()
        self.log_window = None
        self.log_window_text = None

    def sync_log_window(self):
        if self.log_window_text is None:
            return
        self.log_window_text.configure(state="normal")
        self.log_window_text.delete("1.0", tk.END)
        for timestamp, line, stage in self.log_history:
            tag = stage if stage in self.log_window_text.tag_names() else "default"
            self.log_window_text.insert(tk.END, f"{timestamp} ", "timestamp")
            self.log_window_text.insert(tk.END, line + "\n", tag)
        self.log_window_text.see(tk.END)
        self.log_window_text.configure(state="disabled")

    def append_log(self, stage, message):
        self._append_log_line(f"[{stage}] {message}", stage)
        self.status_label.configure(text=message)

    def _append_log_line(self, line, stage="default"):
        timestamp = time.strftime("%H:%M:%S")
        self.log_history.append((timestamp, line, stage))
        if self.log_window_text is not None:
            tag = stage if stage in self.log_window_text.tag_names() else "default"
            self.log_window_text.configure(state="normal")
            self.log_window_text.insert(tk.END, f"{timestamp} ", "timestamp")
            self.log_window_text.insert(tk.END, line + "\n", tag)
            self.log_window_text.see(tk.END)
            self.log_window_text.configure(state="disabled")

    def append_process_line(self, line):
        stage = "流程"
        if line.startswith("[") and "]" in line:
            stage = line[1 : line.find("]")]
        self._append_log_line(line, stage)
        self.status_label.configure(text=line)

    def clear_log(self):
        self.log_history.clear()
        if self.log_window_text is not None:
            self.log_window_text.configure(state="normal")
            self.log_window_text.delete("1.0", tk.END)
            self.log_window_text.configure(state="disabled")
        self.append_log("主界面", "日志已清空。")

    def set_runtime_state(self, state, message):
        palette = {
            "idle": ("空闲", APP_THEME["surface_alt"], APP_THEME["muted"]),
            "running": ("运行中", APP_THEME["warning_soft"], APP_THEME["warning"]),
            "success": ("已完成", APP_THEME["success_soft"], APP_THEME["success"]),
            "error": ("出错", APP_THEME["danger_soft"], APP_THEME["danger"]),
        }
        text, bg, fg = palette.get(state, palette["idle"])
        self.runtime_badge.configure(text=text, bg=bg, fg=fg)
        self.runtime_text.configure(text=message)

    def set_busy(self, busy, message=None):
        state = tk.DISABLED if busy else tk.NORMAL
        alive_buttons = []
        for button in self.action_buttons:
            try:
                button.configure(state=state)
                alive_buttons.append(button)
            except tk.TclError:
                continue
        self.action_buttons = alive_buttons
        self.advanced_toggle_button.configure(state=state)
        if message:
            self.status_label.configure(text=message)
        self.set_runtime_state("running" if busy else "idle", message or ("正在处理任务..." if busy else "等待操作"))

    def preview_box_from_json(self):
        if not BOX_WRITE_DATA_FILE.exists():
            messagebox.showwarning(
                "缺少数据",
                f"未找到 {BOX_WRITE_DATA_FILE.name}，请先执行“一键同步 BOX”或“生成 BOX 写入数据”。",
                parent=self.root,
            )
            return
        self.start_subprocess(["--preview-box-json"], "预览 BOX 图")

    def open_mapping_file(self):
        try:
            open_path_with_system(MAPPING_FILE)
            self.append_log("主界面", f"已打开映射表: {MAPPING_FILE.name}")
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc), parent=self.root)

    def open_output_dir(self):
        try:
            open_path_with_system(BASE_DIR)
            self.append_log("主界面", f"已打开输出目录: {BASE_DIR}")
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc), parent=self.root)

    def confirm_clear_login_state(self):
        confirmed = messagebox.askyesno(
            "退出登录",
            "确定要退出当前 B站 登录状态吗？退出后下次运行会重新扫码登录。",
            parent=self.root,
        )
        if not confirmed:
            return
        try:
            removed = clear_login_state()
            if removed:
                messagebox.showinfo("退出完成", "本地登录态已清除，当前账号已退出。", parent=self.root)
            else:
                messagebox.showinfo("无需退出", "当前未发现可清理的登录态文件。", parent=self.root)
            self.refresh_summary_cards()
        except Exception as exc:
            messagebox.showerror("退出失败", str(exc), parent=self.root)

    def start_subprocess(self, extra_args, task_name):
        if self.current_process is not None:
            messagebox.showinfo("任务进行中", "当前已有任务在运行，请等待完成后再试。", parent=self.root)
            return
        if any(arg in extra_args for arg in ("--sync-box", "--update-mapping", "--generate-box-write-data")):
            try:
                load_mapping_table()
            except RuntimeError as exc:
                messagebox.showerror("映射表错误", str(exc), parent=self.root)
                return
        command = build_self_command(extra_args)
        self.append_log("主界面", f"开始执行: {task_name}")
        self.set_busy(True, f"正在执行: {task_name}")
        try:
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            self.current_process = subprocess.Popen(
                command,
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                **get_hidden_subprocess_kwargs(),
            )
        except Exception as exc:
            self.current_process = None
            self.set_busy(False, "启动失败。")
            messagebox.showerror("启动失败", str(exc), parent=self.root)
            return
        self.stdout_thread = threading.Thread(target=self.read_process_output, daemon=True)
        self.stdout_thread.start()

    def read_process_output(self):
        if not self.current_process or not self.current_process.stdout:
            return
        for line in self.current_process.stdout:
            with self.queue_lock:
                self.output_queue.append(line.rstrip("\r\n"))

    def poll_process_output(self):
        with self.queue_lock:
            pending = self.output_queue[:]
            self.output_queue.clear()
        for line in pending:
            if line:
                self.append_process_line(line)
        if self.current_process is not None:
            return_code = self.current_process.poll()
            if return_code is not None:
                self.finish_process(return_code)
        self.root.after(120, self.poll_process_output)

    def finish_process(self, return_code):
        process = self.current_process
        self.current_process = None
        self.stdout_thread = None
        self.set_busy(False, "等待操作")
        self.refresh_summary_cards()
        if process and process.stdout:
            try:
                process.stdout.close()
            except Exception:
                pass
        if return_code == 0:
            self.append_log("主界面", "任务执行完成。")
            self.set_runtime_state("success", "最近一次任务已完成")
        else:
            self.append_log("主界面", f"任务执行失败，退出码: {return_code}")
            self.set_runtime_state("error", f"任务失败，退出码 {return_code}")
            messagebox.showerror("执行失败", f"任务执行失败，退出码: {return_code}", parent=self.root)

    def interrupt_current_process(self):
        process = self.current_process
        self.current_process = None
        self.stdout_thread = None
        if process is None:
            return True
        self.append_log("主界面", "正在中断后台任务...")
        stopped = terminate_process_tree(process)
        if stopped:
            self.append_log("主界面", "后台任务已中断。")
            self.set_runtime_state("error", "后台任务已手动中断")
        else:
            self.append_log("主界面", "后台任务中断失败，进程可能仍在运行。")
            self.set_runtime_state("error", "后台任务中断失败")
        return stopped

    def handle_close(self):
        if self.current_process is not None:
            choice = messagebox.askyesnocancel(
                "退出确认",
                "当前仍有任务在运行。\n\n选择“是”会关闭界面并中断任务。\n选择“否”只关闭界面，后台任务继续运行。\n选择“取消”则返回主界面。",
                parent=self.root,
            )
            if choice is None:
                return
            if choice:
                self.interrupt_current_process()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

def launch_main_window():
    ensure_dirs()
    load_mapping_table()
    app = MainApp()
    app.run()

def load_auth_state(context, had_existing_profile):
    if had_existing_profile:
        log("登录态", f"检测到本地浏览器配置目录: {USER_DATA_DIR}")
        return True
    if not COOKIE_FILE.exists():
        log("登录态", "未发现旧版 cookie 文件，将走扫码登录。")
        return False
    try:
        with COOKIE_FILE.open("r", encoding="utf-8") as file:
            cookies = json.load(file)
        if cookies:
            context.add_cookies(cookies)
            log("登录态", f"已兼容导入旧版 cookie 文件: {COOKIE_FILE.name}")
            return True
    except Exception as exc:
        log("登录态", f"读取旧版 cookie 文件失败，将重新登录: {exc}")
    return False

def save_auth_state(context):
    try:
        state = context.storage_state()
        with STATE_FILE.open("w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
        with COOKIE_FILE.open("w", encoding="utf-8") as file:
            json.dump(state.get("cookies", []), file, ensure_ascii=False, indent=2)
        log("状态保存", f"已保存 storage_state: {STATE_FILE.name}")
        log("状态保存", f"已更新兼容 cookie 文件: {COOKIE_FILE.name}")
    except Exception as exc:
        raise RuntimeError(f"保存登录态失败: {exc}") from exc

def get_cookie_names(context):
    try:
        return {cookie["name"] for cookie in context.cookies()}
    except Exception:
        return set()

def fetch_nav_info(context, page=None):
    last_error = None
    try:
        response = context.request.get(NAV_API_URL, timeout=10000)
        data = response.json()
        if isinstance(data, dict):
            return data
    except Exception as exc:
        last_error = exc
    if page is not None:
        try:
            return page.evaluate(
                """async (url) => {
                    const response = await fetch(url, {
                        method: 'GET',
                        credentials: 'include'
                    });
                    return await response.json();
                }""",
                NAV_API_URL,
            )
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"读取登录状态接口失败: {last_error}")

def get_login_status(context, page=None):
    cookie_names = get_cookie_names(context)
    has_session_cookies = LOGIN_COOKIE_NAMES.issubset(cookie_names)
    try:
        nav_info = fetch_nav_info(context, page)
        data = nav_info.get("data") or {}
        is_login = bool(data.get("isLogin"))
        username = data.get("uname") or ""
        return {
            "is_login": is_login,
            "username": username,
            "source": "接口检测",
            "has_session_cookies": has_session_cookies,
        }
    except Exception as exc:
        return {
            "is_login": has_session_cookies,
            "username": "",
            "source": f"Cookie 回退 ({exc})",
            "has_session_cookies": has_session_cookies,
        }

def is_logged_in(context, page=None, verbose=True):
    status = get_login_status(context, page)
    if verbose:
        if status["is_login"]:
            name_suffix = f" 用户: {status['username']}" if status["username"] else ""
            log("登录检测", f"已登录，来源: {status['source']}.{name_suffix}")
        else:
            log("登录检测", f"未登录，来源: {status['source']}")
    return status["is_login"]

def get_working_page(context):
    if context.pages:
        page = context.pages[0]
    else:
        page = context.new_page()
    page.set_default_timeout(DEFAULT_TIMEOUT_MS)
    return page

def click_first_visible(page, selectors, timeout_ms=1500):
    for frame in page.frames:
        for selector in selectors:
            locator = frame.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=timeout_ms)
                locator.click()
                return True, selector, frame.url
            except Exception:
                continue
    return False, None, None

def find_first_visible_locator(page, selectors, timeout_ms=2000):
    for frame in page.frames:
        for selector in selectors:
            locator = frame.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=timeout_ms)
                return locator, selector, frame.url
            except Exception:
                continue
    return None, None, None

def get_page_text(page):
    texts = []
    for frame in page.frames:
        try:
            text = frame.evaluate("() => document.body ? document.body.innerText : ''")
        except Exception:
            continue
        if text:
            texts.append(text)
    return "\n".join(texts)

def open_login_page(page):
    log("登录页", "正在打开 B 站登录页...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=LOGIN_PAGE_IDLE_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log("登录页", "networkidle 等待超时，继续后续步骤。")
    clicked, selector, frame_url = click_first_visible(page, QR_TAB_SELECTORS)
    if clicked:
        log("登录页", f"已切换到扫码登录，匹配选择器: {selector}")
    else:
        log("登录页", "未找到扫码登录切换按钮，将直接尝试抓取二维码。")
    if frame_url:
        log("登录页", f"二维码登录区域所在页面: {frame_url}")

def capture_qr_image(page, output_path=None):
    locator, selector, frame_url = find_first_visible_locator(
        page,
        QR_IMAGE_SELECTORS,
        timeout_ms=QR_SELECTOR_TIMEOUT_MS,
    )
    if locator is None:
        raise RuntimeError("未找到可见的二维码元素，请检查登录页结构是否变更。")
    if output_path is None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
    else:
        temp_path = Path(output_path)
    locator.screenshot(path=str(temp_path))
    log("二维码", f"已抓取二维码，匹配选择器: {selector}")
    if frame_url:
        log("二维码", f"二维码所在页面: {frame_url}")
    return temp_path

def is_qr_expired(page):
    page_text = get_page_text(page)
    return any(keyword in page_text for keyword in QR_EXPIRED_KEYWORDS)

def refresh_qr(page, qr_path, popup):
    popup.set_status("二维码已过期，正在尝试刷新...", "#C62828")
    clicked, selector, _ = click_first_visible(page, QR_REFRESH_SELECTORS, timeout_ms=1200)
    if not clicked:
        popup.set_status("二维码已过期，请重新运行脚本", "#C62828")
        return False
    log("二维码", f"检测到过期，已点击刷新: {selector}")
    page.wait_for_timeout(800)
    capture_qr_image(page, output_path=qr_path)
    popup.refresh_image()
    popup.set_status("二维码已刷新，请重新扫码", "#C62828")
    return True

def wait_for_login_success(context, page, popup, timeout_seconds=LOGIN_WAIT_TIMEOUT_SECONDS):
    log("登录等待", "请使用 B 站 App 扫码，并在手机上确认登录。")
    deadline = time.monotonic() + timeout_seconds
    last_source = None
    last_url = None
    qr_expired = False
    while time.monotonic() < deadline:
        popup.process_events()
        status = get_login_status(context, page)
        current_url = page.url
        if status["is_login"]:
            name_suffix = f" 用户: {status['username']}" if status["username"] else ""
            log("登录等待", f"登录成功，来源: {status['source']}.{name_suffix}")
            popup.close()
            return
        if popup.closed:
            raise RuntimeError("二维码窗口已关闭，登录流程已取消。")
        if is_qr_expired(page):
            if not qr_expired:
                log("二维码", "检测到当前二维码已过期。")
                refresh_qr(page, popup.image_path, popup)
                qr_expired = True
            time.sleep(LOGIN_POLL_INTERVAL_SECONDS)
            continue
        if qr_expired:
            popup.set_status("请在手机上确认登录", "#666666")
            qr_expired = False
        if status["source"] != last_source or current_url != last_url:
            log("登录等待", f"尚未登录，当前页: {current_url}，检测来源: {status['source']}")
            last_source = status["source"]
            last_url = current_url
        time.sleep(LOGIN_POLL_INTERVAL_SECONDS)
    raise RuntimeError("等待扫码登录超时，请重试。")

def is_box_transient_navigation_error(exc):
    message = str(exc or "").lower()
    return any(
        marker in message
        for marker in (
            "execution context was destroyed",
            "frame was detached",
            "navigat",
            "context was destroyed",
        )
    )

def read_box_page_state(page, button_texts=None):
    button_texts = list(button_texts or [])
    try:
        return page.evaluate(
            """([regions, selectors, keywords, buttonTexts, downloadIconPrefix]) => {
                const serializeRect = (node) => {
                    if (!node) return null;
                    const rect = node.getBoundingClientRect();
                    if (!rect || rect.width < 1 || rect.height < 1) return null;
                    return {
                        text: (node.innerText || node.textContent || '').trim(),
                        tag: node.tagName || '',
                        className: node.className || '',
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height,
                        area: rect.width * rect.height,
                    };
                };

                const isVisible = (node) => {
                    if (!node) return false;
                    const rect = node.getBoundingClientRect();
                    if (!rect || rect.width < 1 || rect.height < 1) return false;
                    const style = window.getComputedStyle(node);
                    if (!style) return false;
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    return true;
                };

                const text = document.body ? (document.body.innerText || '') : '';
                const title = document.title || '';
                const bodyNodes = Array.from(document.querySelectorAll('body *')).filter(isVisible);

                const exactButtons = bodyNodes
                    .map((node) => {
                        const value = (node.innerText || node.textContent || '').trim();
                        if (!buttonTexts.includes(value)) return null;
                        const rect = serializeRect(node);
                        if (!rect) return null;
                        return rect;
                    })
                    .filter(Boolean)
                    .sort((a, b) => a.area - b.area);

                const fixedElements = bodyNodes
                    .map((el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return {
                            node: el,
                            text: (el.innerText || el.textContent || '').trim(),
                            position: style.position,
                            width: rect.width,
                            height: rect.height,
                            area: rect.width * rect.height,
                        };
                    })
                    .filter((item) => item.position === 'fixed');

                const expandedToolbars = fixedElements
                    .filter((item) => item.width > 150 && item.height > 500)
                    .sort((a, b) => b.area - a.area);
                const collapsedToolbars = fixedElements
                    .filter((item) =>
                        item.width >= 40
                        && item.width <= 100
                        && item.height >= 100
                        && item.height <= 180
                        && (item.text.includes('＜') || item.text.includes('<'))
                    )
                    .sort((a, b) => a.area - b.area);

                const regionCandidates = expandedToolbars.length
                    ? Array.from(expandedToolbars[0].node.children)
                        .filter(isVisible)
                        .map((node) => {
                            const value = (node.innerText || node.textContent || '').trim();
                            const rect = serializeRect(node);
                            return regions.includes(value) && rect ? { value, rect } : null;
                        })
                        .filter(Boolean)
                    : [];
                const regionButtons = {};
                regionCandidates.forEach((item) => {
                    regionButtons[item.value] = item.rect;
                });
                const region = regionCandidates.length === 1 ? regionCandidates[0].value : 'unknown';

                let toolbarState = 'unknown';
                if (expandedToolbars.length) toolbarState = 'expanded';
                else if (collapsedToolbars.length) toolbarState = 'collapsed';

                let toolbarToggleRect = null;
                if (expandedToolbars.length && expandedToolbars[0].node.children.length) {
                    toolbarToggleRect = serializeRect(expandedToolbars[0].node.children[0]);
                }
                if (!toolbarToggleRect && collapsedToolbars.length) {
                    toolbarToggleRect = serializeRect(collapsedToolbars[0].node);
                }

                let downloadRect = null;
                let downloadStrategy = '';
                if (expandedToolbars.length) {
                    const toolbarNode = expandedToolbars[0].node;
                    const downloadCandidates = Array.from(toolbarNode.children)
                        .filter(isVisible)
                        .map((node) => {
                            const rect = serializeRect(node);
                            if (!rect || rect.width < 40 || rect.height < 40) return null;
                            const style = window.getComputedStyle(node);
                            const textValue = (node.innerText || node.textContent || '').trim();
                            const titleValue = (node.getAttribute('title') || '').trim();
                            const ariaValue = (node.getAttribute('aria-label') || '').trim();
                            const classValue = String(node.className || '').trim();
                            const idValue = (node.id || '').trim();
                            const bgValue = style.backgroundImage || '';
                            const hintText = `${textValue} ${titleValue} ${ariaValue} ${classValue} ${idValue}`.toLowerCase();
                            return {
                                rect,
                                icon: !textValue && bgValue.includes(downloadIconPrefix),
                                semantic: /(?:^|[\\s_-])(?:download|save|export)(?:$|[\\s_-])|下载|保存|导出/.test(hintText),
                            };
                        })
                        .filter(Boolean);
                    const iconMatches = downloadCandidates.filter((item) => item.icon);
                    const semanticMatches = downloadCandidates.filter((item) => item.semantic);
                    if (iconMatches.length === 1) {
                        downloadRect = iconMatches[0].rect;
                        downloadStrategy = 'icon';
                    } else if (!iconMatches.length && semanticMatches.length === 1) {
                        downloadRect = semanticMatches[0].rect;
                        downloadStrategy = 'semantic';
                    }
                }

                let readyKind = '';
                let readyValue = '';
                if (region !== 'unknown') {
                    readyKind = 'region';
                    readyValue = region;
                } else if (toolbarState !== 'unknown') {
                    readyKind = 'toolbar';
                    readyValue = toolbarState;
                } else {
                    for (const selector of selectors) {
                        const node = document.querySelector(selector);
                        if (isVisible(node)) {
                            readyKind = 'selector';
                            readyValue = selector;
                            break;
                        }
                    }
                    if (!readyKind) {
                        const keyword = keywords.find((item) => text.includes(item) || title.includes(item));
                        if (keyword) {
                            readyKind = 'keyword';
                            readyValue = keyword;
                        }
                    }
                }

                return {
                    region,
                    toolbarState,
                    readyKind,
                    readyValue,
                    toolbarToggleRect,
                    downloadRect,
                    downloadStrategy,
                    buttonCandidates: exactButtons,
                    regionButtons,
                };
            }""",
            [list(BOX_REGION_OPTIONS), BOX_READY_SELECTORS, BOX_READY_KEYWORDS,
             button_texts, BOX_DOWNLOAD_ICON_PREFIX],
        ) or {}
    except Exception as exc:
        if is_box_transient_navigation_error(exc):
            return {
                "region": "unknown",
                "toolbarState": "unknown",
                "readyKind": "",
                "readyValue": "",
                "toolbarToggleRect": None,
                "downloadRect": None,
                "downloadStrategy": "",
                "buttonCandidates": [],
                "regionButtons": {},
            }
        raise

def wait_box_page_ready(page, timeout_ms=BOX_READY_TIMEOUT_MS):
    deadline = time.time() + timeout_ms / 1000
    last_error = None
    while time.time() < deadline:
        try:
            state = read_box_page_state(page)
            ready_kind = state.get("readyKind") or "unknown"
            ready_value = state.get("readyValue") or "unknown"
            if ready_kind == "unknown":
                page.wait_for_timeout(200)
                continue
            log("BOX页面", f"页面已就绪，命中 {ready_kind}: {ready_value}")
            return state
        except Exception as exc:
            last_error = exc
            if is_box_transient_navigation_error(exc):
                page.wait_for_timeout(150)
                continue
            raise RuntimeError(f"BOX 图页面未就绪: {exc}") from exc
    raise RuntimeError(f"BOX 图页面未就绪: {last_error}")

def find_box_button_rect(page, target_texts):
    try:
        state = read_box_page_state(page, button_texts=target_texts)
        candidates = state.get("buttonCandidates") or []
        return candidates[0] if candidates else None
    except Exception as exc:
        if is_box_transient_navigation_error(exc):
            return None
        raise

def click_box_rect(page, rect, description, min_size=BOX_BUTTON_MIN_SIZE):
    if not rect:
        raise RuntimeError(f"未找到 {description} 按钮。")
    if rect["width"] < min_size or rect["height"] < min_size:
        raise RuntimeError(
            f"{description} 按钮尺寸异常: {rect['width']}x{rect['height']}"
        )
    click_x = rect["x"] + rect["width"] / 2
    click_y = rect["y"] + rect["height"] / 2
    page.mouse.click(click_x, click_y)
    log(
        "BOX页面",
        f"已点击{description}按钮: 文本={rect['text']} 坐标=({click_x:.1f}, {click_y:.1f})",
    )
    return rect

def detect_box_region(page):
    try:
        return read_box_page_state(page).get("region") or "unknown"
    except Exception as exc:
        if is_box_transient_navigation_error(exc):
            return "unknown"
        raise

def click_box_region_button(page, region):
    state = read_box_page_state(page)
    rect = (state.get("regionButtons") or {}).get(region)
    return click_box_rect(page, rect, f"{region}语言切换")

def wait_box_region_switch_stable(page, previous_region, timeout_ms=BOX_REGION_SWITCH_TIMEOUT_MS):
    deadline = time.time() + timeout_ms / 1000
    last_error = None
    refresh_logged = False
    while time.time() < deadline:
        remaining_ms = max(300, int((deadline - time.time()) * 1000))
        try:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=min(remaining_ms, BOX_DOMCONTENTLOADED_TIMEOUT_MS))
            except PlaywrightTimeoutError:
                pass
            state = wait_box_page_ready(page, timeout_ms=min(remaining_ms, BOX_REGION_SWITCH_TIMEOUT_MS))
            current = state.get("region") or "unknown"
            if current == "CN":
                return current
            if current not in ("unknown", previous_region):
                log("BOX页面", f"语言切换后当前语言状态: {current}")
        except RuntimeError as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc
            if is_box_transient_navigation_error(exc):
                if not refresh_logged:
                    log("BOX页面", "语言切换触发页面刷新，等待页面重新稳定...")
                    refresh_logged = True
                page.wait_for_timeout(250)
                continue
            raise
        page.wait_for_timeout(250)
    current = detect_box_region(page)
    if current != "CN":
        raise RuntimeError(f"切换到 CN 失败，当前语言状态: {current}") from last_error
    return current

def ensure_box_region_cn(page):
    last_state = None
    for _ in range(1, 7):
        state = read_box_page_state(page, button_texts=list(BOX_REGION_OPTIONS))
        last_state = state
        current = state.get("region") or "unknown"
        toolbar_state = state.get("toolbarState") or "unknown"
        log("BOX页面", f"当前语言状态: {current}")
        if current == "CN":
            return "CN"
        if current in ("JP", "EN"):
            rect = (state.get("regionButtons") or {}).get(current)
            click_box_rect(page, rect, f"{current}语言切换")
            return wait_box_region_switch_stable(page, current)
        if toolbar_state == "collapsed":
            log("BOX页面", "语言按钮当前不可见，先展开工具栏再继续判断。")
            ensure_box_toolbar_expanded(page)
            continue
        page.wait_for_timeout(300)
    current = (last_state or {}).get("region") or detect_box_region(page)
    if current != "CN":
        raise RuntimeError(f"切换到 CN 失败，当前语言状态: {current}")
    return current

def detect_box_toolbar_state(page):
    try:
        return read_box_page_state(page).get("toolbarState") or "unknown"
    except Exception as exc:
        if is_box_transient_navigation_error(exc):
            return "unknown"
        raise

def get_box_toolbar_toggle_rect(page):
    return read_box_page_state(page).get("toolbarToggleRect")

def toggle_box_toolbar(page):
    rect = get_box_toolbar_toggle_rect(page)
    click_box_rect(page, rect, "工具栏切换")
    page.wait_for_timeout(900)

def ensure_box_toolbar_collapsed(page):
    last_state = "unknown"
    for _ in range(4):
        state = detect_box_toolbar_state(page)
        last_state = state
        log("BOX页面", f"当前工具栏状态: {state}")
        if state == "collapsed":
            return state
        if state == "expanded":
            toggle_box_toolbar(page)
            page.wait_for_timeout(200)
            continue
        page.wait_for_timeout(200)
    raise RuntimeError(f"折叠工具栏失败，当前状态: {last_state}")

def ensure_box_toolbar_expanded(page):
    last_state = "unknown"
    for _ in range(4):
        state = detect_box_toolbar_state(page)
        last_state = state
        log("BOX页面", f"当前工具栏状态: {state}")
        if state == "expanded":
            return state
        if state == "collapsed":
            toggle_box_toolbar(page)
            page.wait_for_timeout(200)
            continue
        page.wait_for_timeout(200)
    raise RuntimeError(f"展开工具栏失败，当前状态: {last_state}")

def find_box_download_rect(page):
    state = read_box_page_state(page)
    rect = state.get("downloadRect")
    strategy = state.get("downloadStrategy")
    if rect and strategy:
        log("BOX页面", f"下载按钮命中策略: {strategy}")
    return rect

def apply_box_write_data(page, write_data):
    if not write_data:
        raise RuntimeError("BOX 写入数据为空，无法同步。")
    log("BOX同步", f"准备写入 {len(write_data)} 条 BOX 数据到 localStorage。")
    page.evaluate(
        """(data) => {
            Object.entries(data).forEach(([key, value]) => {
                localStorage.setItem(key, String(value));
            });
        }""",
        write_data,
    )
    page.reload(wait_until="domcontentloaded", timeout=max(PAGE_LOAD_TIMEOUT_MS, BOX_WRITE_APPLY_TIMEOUT_MS))
    try:
        page.wait_for_load_state("networkidle", timeout=BOX_PAGE_IDLE_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log("BOX同步", "reload 后 networkidle 等待超时，继续后续步骤。")
    wait_box_page_ready(page, timeout_ms=BOX_WRITE_APPLY_TIMEOUT_MS)
    ensure_box_region_cn(page)
    log("BOX同步", "BOX 数据写入完成并已刷新页面。")

def capture_box_preview(page, output_path=None):
    ensure_box_region_cn(page)
    ensure_box_toolbar_collapsed(page)
    if output_path is None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            preview_path = Path(temp_file.name)
    else:
        preview_path = Path(output_path)
    page.screenshot(path=str(preview_path), full_page=True)
    log("BOX页面", f"预览图已生成: {preview_path}")
    return preview_path

def show_box_preview_popup(preview_path, element_path=None, element_error=None):
    popup = BoxPreviewPopup(preview_path, element_path, element_error)
    popup.open()
    log("BOX页面", "预览窗口已弹出，请选择下载、另存位置或直接关闭窗口。")
    try:
        return popup.wait_for_choice()
    finally:
        popup.close()

def make_box_output_path(save_dir, suffix=""):
    target_dir = Path(save_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return target_dir / f"box图_{timestamp}{suffix}.png"

def flatten_png_with_black_background(image_path):
    image_path = Path(image_path)
    with Image.open(image_path) as image:
        rgba = image.convert("RGBA")
        black_background = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        merged = Image.alpha_composite(black_background, rgba).convert("RGB")
        merged.save(image_path)
    log("BOX页面", f"已为导出图片铺黑底: {image_path}")
    return image_path

def download_box_image_to_path(page, target_path):
    ensure_box_region_cn(page)
    ensure_box_toolbar_expanded(page)
    rect = find_box_download_rect(page)
    if not rect:
        raise RuntimeError("未定位到下载按钮。")
    with page.expect_download(timeout=BOX_DOWNLOAD_TIMEOUT_MS) as download_info:
        click_box_rect(page, rect, "下载")
    download = download_info.value
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    download.save_as(str(target_path))
    flatten_png_with_black_background(target_path)
    log("BOX页面", f"BOX 图已下载到: {target_path}")
    return target_path

def download_box_image(page, save_dir):
    target_path = make_box_output_path(save_dir)
    return download_box_image_to_path(page, target_path)

def create_temp_box_download_path():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
        return Path(temp_file.name)

def finalize_temp_box_download(temp_path, save_dir):
    temp_path = Path(temp_path)
    target_path = make_box_output_path(save_dir)
    shutil.move(str(temp_path), str(target_path))
    log("BOX页面", f"已将预览下载图保存到: {target_path}")
    return target_path

def ask_download_fallback():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return messagebox.askyesno(
            "下载失败",
            "网站下载失败，是否改用折叠工具栏后的截图作为兜底导出？",
            parent=root,
        )
    finally:
        root.destroy()

def ask_box_open_retry(error_message):
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return messagebox.askyesno(
            "BOX 网站打开失败",
            f"暂时无法打开 BOX 网站。\n\n错误信息：{error_message}\n\n是否立即重试？",
            parent=root,
        )
    finally:
        root.destroy()

def save_box_screenshot_fallback(page, save_dir):
    ensure_box_region_cn(page)
    ensure_box_toolbar_collapsed(page)
    target_path = make_box_output_path(save_dir, BOX_FALLBACK_SUFFIX)
    page.screenshot(path=str(target_path), full_page=True)
    log("BOX页面", f"已保存截图兜底文件: {target_path}")
    return target_path

def cleanup_temp_file(path):
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass

def capture_box_initial_state(page):
    ensure_box_region_cn(page)
    ensure_box_toolbar_collapsed(page)
    page.screenshot(path=str(BOX_INITIAL_SCREENSHOT_FILE), full_page=True)
    log("BOX页面", f"初始状态截图已保存到: {BOX_INITIAL_SCREENSHOT_FILE}")
    return BOX_INITIAL_SCREENSHOT_FILE

def open_box_site(page):
    log("BOX页面", "正在进入 BOX 图网站...")
    cycle = 1
    while True:
        last_error = None
        for attempt in range(1, BOX_GOTO_RETRY_COUNT + 1):
            try:
                log("BOX页面", f"正在进入 BOX 图网站（第 {cycle} 轮，第 {attempt}/{BOX_GOTO_RETRY_COUNT} 次）...")
                response = page.goto(BOX_URL, wait_until="commit", timeout=BOX_GOTO_TIMEOUT_MS)
                if response is not None:
                    log("BOX页面", f"BOX 站点响应状态: {response.status}")
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=BOX_DOMCONTENTLOADED_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    log("BOX页面", "domcontentloaded 等待超时，继续等待页面关键内容。")
                try:
                    page.wait_for_load_state("networkidle", timeout=BOX_PAGE_IDLE_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    log("BOX页面", "networkidle 等待超时，继续后续步骤。")
                wait_box_page_ready(page)
                ensure_box_region_cn(page)
                log("BOX页面", f"已进入: {page.url}")
                return
            except PlaywrightTimeoutError as exc:
                last_error = exc
                log("BOX页面", f"第 {cycle} 轮打开 BOX 超时: {exc}")
            except Exception as exc:
                last_error = exc
                log("BOX页面", f"第 {cycle} 轮打开 BOX 失败: {exc}")
            if attempt < BOX_GOTO_RETRY_COUNT:
                try:
                    page.goto("about:blank", wait_until="commit", timeout=5000)
                except Exception:
                    pass
                page.wait_for_timeout(BOX_GOTO_RETRY_WAIT_MS)
        error_message = str(last_error) if last_error else "未知错误"
        if not ask_box_open_retry(error_message):
            raise RuntimeError("用户取消重试 BOX 网站")
        cycle += 1
        log("BOX页面", "用户选择重试，准备再次打开 BOX 网站...")
        try:
            page.goto("about:blank", wait_until="commit", timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(BOX_GOTO_RETRY_WAIT_MS)

def cleanup_element_future(element_future):
    try:
        cleanup_temp_file(element_future.result())
    except Exception:
        pass


def run_box_preview_download(write_data=None, element_future=None, headless=None):
    ensure_dirs()
    if headless is None:
        headless = browser_headless()
    if element_future is not None:
        return _run_box_preview_download(write_data, element_future, headless)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="element-box") as executor:
        log("属性BOX", "正在并行生成按属性分类的 BOX 图...")
        element_future = executor.submit(create_element_box_preview, headless)
        try:
            return _run_box_preview_download(write_data, element_future, headless)
        finally:
            cleanup_element_future(element_future)


def _run_box_preview_download(write_data, element_future, headless):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=headless,
            args=[f"--window-size={VIEWPORT['width']},{VIEWPORT['height']}"],
        )
        context = browser.new_context(
            viewport=VIEWPORT,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )
        page = context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT_MS)
        preview_path = None
        element_path = None
        preview_is_download = False
        try:
            open_box_site(page)
            if write_data is not None:
                apply_box_write_data(page, write_data)
            try:
                preview_path = create_temp_box_download_path()
                preview_path = download_box_image_to_path(page, preview_path)
                preview_is_download = True
                log("BOX页面", "预览图已直接使用网站下载结果。")
            except Exception as exc:
                cleanup_temp_file(preview_path)
                preview_path = None
                preview_is_download = False
                log("BOX页面", f"预览下载失败，改用截图预览: {exc}")
                preview_path = capture_box_preview(page)
            element_error = None
            try:
                element_path = element_future.result()
                log("属性BOX", "属性 BOX 图已生成，可与原版 BOX 图切换预览。")
            except Exception as exc:
                cleanup_temp_file(element_path)
                element_path = None
                element_error = str(exc)
                log("属性BOX", f"属性 BOX 图生成失败，仍可预览原版 BOX 图: {exc}")
            choice, selected_dir = show_box_preview_popup(preview_path, element_path, element_error)
            if choice not in ("original", "element", "both", "download"):
                log("BOX页面", "预览窗口已关闭，本次不执行下载。")
                return None
            save_dir = selected_dir or BOX_OUTPUT_DIR
            saved = {}
            if choice in ("original", "both", "download"):
                try:
                    if preview_is_download:
                        saved["original"] = finalize_temp_box_download(preview_path, save_dir)
                        preview_path = None
                    else:
                        saved["original"] = download_box_image(page, save_dir)
                except Exception as exc:
                    log("BOX页面", f"网站下载失败: {exc}")
                    if ask_download_fallback():
                        saved["original"] = save_box_screenshot_fallback(page, save_dir)
                    else:
                        raise RuntimeError("原版 BOX 图下载失败，且用户未选择截图兜底。") from exc
            if choice in ("element", "both"):
                if element_path is None:
                    raise RuntimeError("属性 BOX 图尚未生成，无法下载。")
                target = make_box_output_path(save_dir, "_属性")
                shutil.move(str(element_path), str(target))
                element_path = None
                saved["element"] = target
                log("属性BOX", f"属性 BOX 图已保存到: {target}")
            return saved if choice == "both" else next(iter(saved.values()))
        except Exception as exc:
            log("错误", str(exc))
            try:
                save_debug_screenshot(page, "box_preview_download_error")
            except Exception:
                log("调试截图", "当前 BOX 页面无法保存调试截图。")
            raise
        finally:
            cleanup_temp_file(preview_path)
            cleanup_temp_file(element_path)
            context.close()
            browser.close()

def run_box_initial_shot():
    ensure_dirs()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=browser_headless(),
            args=[f"--window-size={VIEWPORT['width']},{VIEWPORT['height']}"],
        )
        context = browser.new_context(
            viewport=VIEWPORT,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT_MS)
        try:
            open_box_site(page)
            return capture_box_initial_state(page)
        except Exception as exc:
            log("错误", str(exc))
            try:
                save_debug_screenshot(page, "box_initial_shot_error")
            except Exception:
                log("调试截图", "当前 BOX 页面无法保存调试截图。")
            raise
        finally:
            context.close()
            browser.close()

def open_hbr_page(page):
    log("HBR页面", "正在进入 HBR 页面...")
    page.goto(HBR_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=HBR_PAGE_IDLE_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        log("HBR页面", "networkidle 等待超时，继续后续步骤。")
    log("HBR页面", f"已进入: {page.url}")

def get_hbr_card_stats(page):
    return page.evaluate(
        f"""() => {{
            const elements = document.querySelectorAll('{HBR_CARD_SELECTOR}');
            let withDataId = 0;
            let withRarity = 0;
            elements.forEach((el) => {{
                if (el.dataset && el.dataset.id) withDataId += 1;
                if (el.querySelector('.role-rarity')) withRarity += 1;
            }});
            return {{
                total: elements.length,
                withDataId,
                withRarity,
                title:
                    document.querySelector('.header .title')?.textContent
                    || document.querySelector('.title')?.textContent
                    || '',
            }};
        }}"""
    )

def click_text_in_page(page, target_text):
    return page.evaluate(
        """(targetText) => {
            const buildRect = (rect) => ({
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
            });
            const dispatchClick = (node) => {
                if (!node) return false;
                try {
                    node.scrollIntoView({ block: 'center', inline: 'center' });
                } catch (error) {}
                const rect = node.getBoundingClientRect();
                if (!rect || rect.width < 2 || rect.height < 2) return false;
                const events = ['pointerdown', 'mousedown', 'mouseup', 'click'];
                for (const eventName of events) {
                    node.dispatchEvent(
                        new MouseEvent(eventName, {
                            bubbles: true,
                            cancelable: true,
                            clientX: rect.left + rect.width / 2,
                            clientY: rect.top + rect.height / 2,
                            view: window,
                        })
                    );
                }
                if (typeof node.click === 'function') {
                    node.click();
                }
                return {
                    clicked: true,
                    text: (node.innerText || node.textContent || '').trim(),
                    tag: node.tagName || '',
                    className: node.className || '',
                    rect: buildRect(rect),
                    source: 'element',
                };
            };
            const visibleElements = Array.from(document.querySelectorAll('body *'))
                .map((node) => {
                    const text = (node.innerText || node.textContent || '').trim();
                    if (!text || !text.includes(targetText)) return null;
                    const rect = node.getBoundingClientRect();
                    if (!rect || rect.width < 6 || rect.height < 6) return null;
                    const style = window.getComputedStyle(node);
                    if (!style || style.visibility === 'hidden' || style.display === 'none') return null;
                    return {
                        node,
                        text,
                        rect,
                        area: rect.width * rect.height,
                        textLength: text.length,
                    };
                })
                .filter(Boolean)
                .sort((a, b) => a.textLength - b.textLength || a.area - b.area);
            if (visibleElements.length) {
                return dispatchClick(visibleElements[0].node);
            }
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            const ranges = [];
            while (walker.nextNode()) {
                const node = walker.currentNode;
                const text = (node.nodeValue || '').trim();
                if (!text || !text.includes(targetText)) continue;
                const parent = node.parentElement;
                if (!parent) continue;
                const index = node.nodeValue.indexOf(targetText);
                const range = document.createRange();
                range.setStart(node, index);
                range.setEnd(node, index + targetText.length);
                const rect = range.getBoundingClientRect();
                if (!rect || rect.width < 2 || rect.height < 2) continue;
                ranges.push({
                    parent,
                    text,
                    rect,
                    area: rect.width * rect.height,
                });
            }
            ranges.sort((a, b) => a.area - b.area);
            if (!ranges.length) return { clicked: false, source: 'none' };
            const rangeTarget = ranges[0];
            return dispatchClick(rangeTarget.parent) || { clicked: false, source: 'range' };
        }""",
        target_text,
    )

def click_hbr_tab(page, tab_name):
    tab = page.get_by_role("tab", name=tab_name, exact=True)
    try:
        tab.first.wait_for(state="visible", timeout=HBR_SELECTOR_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(f"点击 HBR 页签失败: {tab_name} 匹配到 0 个页签") from exc
    count = tab.count()
    if count != 1:
        raise RuntimeError(f"点击 HBR 页签失败: {tab_name} 匹配到 {count} 个页签")
    if tab.get_attribute("aria-selected") != "true":
        tab.click(timeout=HBR_SELECTOR_TIMEOUT_MS)
        log("HBR档案", f"已点击页签: {tab_name}")
    return {"clicked": True, "text": tab_name}

def prepare_hbr_page_for_extract(page):
    for attempt in range(1, HBR_PREPARE_RETRIES + 1):
        click_text_in_page(page, "养成助手")
        page.wait_for_timeout(300)
        click_text_in_page(page, "全部风格")
        page.wait_for_timeout(600)
        stats = get_hbr_card_stats(page)
        log(
            "HBR更新",
            f"预热第 {attempt} 轮: total={stats['total']} data-id={stats['withDataId']} rarity={stats['withRarity']} title={stats['title']}",
        )
        if stats["withDataId"] > 0 and stats["withRarity"] > 0:
            return
        if attempt < HBR_PREPARE_RETRIES:
            page.reload(wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            page.wait_for_timeout(800)
    raise RuntimeError("HBR 页面预热失败，未找到可抓取的角色卡片。")

def open_hbr_archive_page(page):
    last_text = ""
    click_hbr_tab(page, "档案")
    deadline = time.monotonic() + HBR_ARCHIVE_READY_TIMEOUT_MS / 1000
    while time.monotonic() < deadline:
        last_text = get_page_text(page)
        if any(keyword in last_text for keyword in HBR_ARCHIVE_READY_KEYWORDS):
            log("HBR档案", "档案页内容已出现。")
            return
        page.wait_for_timeout(250)
    raise RuntimeError(
        "进入档案页失败，未检测到预期关键字。当前页面文本片段: "
        + last_text[:200].replace("\n", " ")
    )

def open_hbr_archive_all_view(page):
    last_error = None
    for attempt in range(1, 3):
        try:
            open_hbr_archive_page(page)
            view_all = page.get_by_text(HBR_ARCHIVE_VIEW_ALL_TEXT, exact=True).filter(visible=True).first
            view_all.click(timeout=HBR_ARCHIVE_VIEW_ALL_TIMEOUT_MS)
            log(
                "HBR档案",
                f"第 {attempt} 次已点击“{HBR_ARCHIVE_VIEW_ALL_TEXT}”。",
            )
            return
        except (PlaywrightTimeoutError, RuntimeError) as exc:
            last_error = exc
            if attempt == 2:
                break
            reason = str(exc).splitlines()
            log("HBR档案", f"“{HBR_ARCHIVE_VIEW_ALL_TEXT}”暂未就绪，刷新档案页后重试: {reason[0] if reason else type(exc).__name__}")
            try:
                page.reload(wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                log("HBR档案", "页面刷新较慢，继续等待档案页。")
            try:
                page.wait_for_load_state("networkidle", timeout=HBR_PAGE_IDLE_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                pass
    raise RuntimeError(
        f"未能点击“{HBR_ARCHIVE_VIEW_ALL_TEXT}”（已刷新重试一次），当前页面: {page.url}"
    ) from last_error

def get_visible_hbr_break_data(page):
    return page.evaluate(
        f"""() => {{
            const elements = document.querySelectorAll('{HBR_ARCHIVE_CARD_SELECTOR}');
            const rows = [];
            elements.forEach((el) => {{
                if (!el.querySelector('.level')?.textContent?.trim()) return;
                const rarityImg = el.querySelector('.role-rarity');
                if (!rarityImg) return;
                const src = rarityImg.src || '';
                const dataSrc = rarityImg.getAttribute('data-src') || '';
                const rarityText = `${{src}} ${{dataSrc}}`;
                if (!rarityText.includes('IconRaritySSR') && !rarityText.includes('IconRaritySS')) return;
                const id = (el.dataset.id || '').trim();
                if (!id) return;
                const breakNode = el.querySelector('.limit-break-level div') || el.querySelector('.limit-break-level');
                const breakText = (breakNode?.innerText || breakNode?.textContent || '').trim();
                const matched = breakText.match(/-?\\d+/);
                const breakNum = matched ? parseInt(matched[0], 10) : 0;
                rows.push({{
                    id,
                    breakNum: Number.isFinite(breakNum) ? breakNum : 0,
                    hasBreakText: !!breakText,
                }});
            }});
            return rows;
        }}"""
    )

def extract_hbr_break_data(page):
    open_hbr_archive_all_view(page)
    page.wait_for_function(
        f"""() => {{
            const elements = document.querySelectorAll('{HBR_ARCHIVE_CARD_SELECTOR}');
            return Array.from(elements).some((el) => {{
                const rarityImg = el.querySelector('.role-rarity');
                return !!(rarityImg && el.dataset.id && el.querySelector('.level')?.textContent?.trim());
            }});
        }}""",
        timeout=max(HBR_SELECTOR_TIMEOUT_MS, 30000),
    )
    collected = {}
    previous_total = -1
    stable_rounds = 0
    no_scroll_rounds = 0
    last_scroll_selector = None
    for round_index in range(1, HBR_SCROLL_MAX_ROUNDS + 1):
        visible_rows = get_visible_hbr_break_data(page)
        with_break_text = 0
        for row in visible_rows:
            row_id = row["id"]
            break_num = int(row["breakNum"])
            if row.get("hasBreakText"):
                with_break_text += 1
            if row_id not in collected:
                collected[row_id] = break_num
            else:
                collected[row_id] = max(collected[row_id], break_num)
        current_total = len(collected)
        if current_total != previous_total:
            stable_rounds = 0
            log(
                "HBR突破",
                f"第 {round_index} 轮累计抓取到 {current_total} 条 SS/SSR 突破数据，本轮可见有效突破文本 {with_break_text} 条。",
            )
        else:
            stable_rounds += 1
        scroll_result = scroll_hbr_page(page)
        moved = bool(scroll_result.get("moved"))
        scroll_selector = scroll_result.get("selector")
        if scroll_selector and scroll_selector != last_scroll_selector:
            log("HBR突破", f"当前使用滚动容器: {scroll_selector}")
            last_scroll_selector = scroll_selector
        if moved:
            no_scroll_rounds = 0
        else:
            no_scroll_rounds += 1
        if stable_rounds >= HBR_STABLE_ROUNDS and no_scroll_rounds >= 2:
            break
        previous_total = current_total
        page.wait_for_timeout(HBR_SCROLL_WAIT_MS)
    rows = [
        {"id": row_id, "breakNum": break_num}
        for row_id, break_num in sorted(collected.items(), key=lambda item: int(item[0]))
    ]
    if not rows:
        raise RuntimeError("档案页未提取到任何 SS/SSR 突破数据，请检查页面是否已正确加载。")
    non_zero_count = sum(1 for row in rows if row["breakNum"] != 0)
    log(
        "HBR突破",
        f"已提取 {len(rows)} 条 SS/SSR 突破数据，其中非 0 突破数 {non_zero_count} 条。",
    )
    return rows

def save_hbr_break_data(rows):
    lines = [f"{row['id']}:{row['breakNum']}" for row in rows]
    HBR_BREAK_DATA_FILE.write_text("\n".join(lines), encoding="utf-8")
    log("HBR突破", f"B站 SS/SSR 突破数据已保存到: {HBR_BREAK_DATA_FILE}")

def run_hbr_break_update(page, enabled=False):
    if not enabled:
        log("HBR突破", "已跳过 B站 SS/SSR 突破数据抓取。")
        return None
    log("HBR突破", "开始抓取 B站 SS/SSR 突破数据...")
    rows = extract_hbr_break_data(page)
    save_hbr_break_data(rows)
    return rows

def get_visible_hbr_ids(page):
    return page.evaluate(
        f"""() => {{
            const elements = document.querySelectorAll('{HBR_CARD_SELECTOR}');
            const ids = [];
            elements.forEach((el) => {{
                const rarityImg = el.querySelector('.role-rarity');
                if (!rarityImg) return;
                const src = rarityImg.src || '';
                const dataSrc = rarityImg.getAttribute('data-src') || '';
                const rarityText = `${{src}} ${{dataSrc}}`;
                if (!rarityText.includes('IconRaritySSR') && !rarityText.includes('IconRaritySS')) return;
                const id = (el.dataset.id || '').trim();
                if (id) ids.push(id);
            }});
            return [...new Set(ids)];
        }}"""
    )

def scroll_hbr_page(page):
    return page.evaluate(
        """([selectors, stepPx]) => {
            for (const selector of selectors) {
                const el = document.querySelector(selector);
                if (!el) continue;
                const maxScrollTop = Math.max(0, el.scrollHeight - el.clientHeight);
                if (maxScrollTop <= 0) continue;
                const before = el.scrollTop || 0;
                const step = Math.max(stepPx, Math.floor((el.clientHeight || 0) * 0.9));
                const next = Math.min(before + step, maxScrollTop);
                el.scrollTo(0, next);
                el.dispatchEvent(new Event('scroll', { bubbles: true }));
                el.dispatchEvent(new WheelEvent('wheel', { deltaY: step, bubbles: true }));
                const after = el.scrollTop || 0;
                if (after > before) {
                    return {
                        moved: true,
                        selector,
                        before,
                        after,
                        maxScrollTop,
                    };
                }
            }
            const root = document.scrollingElement || document.documentElement || document.body;
            const rootMax = Math.max(0, root.scrollHeight - root.clientHeight);
            const rootBefore = root.scrollTop || 0;
            const rootNext = Math.min(rootBefore + stepPx, rootMax);
            root.scrollTo(0, rootNext);
            root.dispatchEvent(new Event('scroll', { bubbles: true }));
            window.scrollBy(0, stepPx);
            const rootAfter = root.scrollTop || 0;
            return {
                moved: rootAfter > rootBefore,
                selector: 'document',
                before: rootBefore,
                after: rootAfter,
                maxScrollTop: rootMax,
            };
        }""",
        [HBR_SCROLL_CONTAINER_SELECTORS, HBR_SCROLL_STEP_PX],
    )

def extract_hbr_ids(page):
    prepare_hbr_page_for_extract(page)
    page.wait_for_function(
        f"""() => {{
            const elements = document.querySelectorAll('{HBR_CARD_SELECTOR}');
            return Array.from(elements).some((el) => {{
                const rarityImg = el.querySelector('.role-rarity');
                if (!rarityImg || !el.dataset.id) return false;
                const src = rarityImg.src || '';
                const dataSrc = rarityImg.getAttribute('data-src') || '';
                const rarityText = `${{src}} ${{dataSrc}}`;
                return rarityText.includes('IconRaritySSR') || rarityText.includes('IconRaritySS');
            }});
        }}""",
        timeout=max(HBR_SELECTOR_TIMEOUT_MS, 30000),
    )
    collected_ids = set()
    previous_total = -1
    stable_rounds = 0
    no_scroll_rounds = 0
    last_scroll_selector = None
    for round_index in range(1, HBR_SCROLL_MAX_ROUNDS + 1):
        visible_ids = get_visible_hbr_ids(page)
        collected_ids.update(visible_ids)
        current_total = len(collected_ids)
        if current_total != previous_total:
            stable_rounds = 0
            log("HBR更新", f"第 {round_index} 轮累计抓取到 {current_total} 个 SS/SSR ID。")
        else:
            stable_rounds += 1
        scroll_result = scroll_hbr_page(page)
        moved = bool(scroll_result.get("moved"))
        scroll_selector = scroll_result.get("selector")
        if scroll_selector and scroll_selector != last_scroll_selector:
            log("HBR更新", f"当前使用滚动容器: {scroll_selector}")
            last_scroll_selector = scroll_selector
        if moved:
            no_scroll_rounds = 0
        else:
            no_scroll_rounds += 1
        if stable_rounds >= HBR_STABLE_ROUNDS and no_scroll_rounds >= 2:
            break
        previous_total = current_total
        page.wait_for_timeout(HBR_SCROLL_WAIT_MS)
    ids = sorted(collected_ids, key=lambda value: int(value))
    if not ids:
        raise RuntimeError("HBR 页面未提取到任何 SS/SSR ID，请检查页面是否已正确加载。")
    log("HBR更新", f"已提取 {len(ids)} 个唯一 SS/SSR ID。")
    return ids

def save_hbr_ids(ids):
    HBR_IDS_FILE.write_text("\n".join(ids), encoding="utf-8")
    log("HBR更新", f"B站 SS/SSR ID 已保存到: {HBR_IDS_FILE}")

def run_hbr_update(page, enabled=False):
    if not enabled:
        log("HBR更新", "已跳过 B站 SS/SSR ID 更新。")
        return None
    log("HBR更新", "开始抓取 B站 SS/SSR ID...")
    ids = extract_hbr_ids(page)
    save_hbr_ids(ids)
    return ids

def run_full_box_sync():
    headless = browser_headless()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="element-box") as executor:
        log("属性BOX", "一键同步开始，正在并行生成按属性分类的 BOX 图...")
        element_future = executor.submit(create_element_box_preview, headless)
        try:
            log("BOX同步", "第 1/3 步：登录并抓取 B站全量 SS/SSR ID 与突破数据...")
            hbr_result = bilibili_login(update_bili_ids=True, update_break_data=True)
            break_rows = hbr_result.get("break_rows") or []
            if not break_rows:
                raise RuntimeError("未获取到 B站 SS/SSR 突破数据，无法同步 BOX 图。")
            log("BOX同步", "第 2/3 步：更新 SS/SSR 映射表...")
            mapping = update_mapping_for_box_sync(hbr_result)
            write_data = build_box_write_data(mapping, break_rows)
            log("BOX同步", "第 3/3 步：打开 BOX 图网站并生成预览图...")
            return run_box_preview_download(
                write_data=write_data, element_future=element_future, headless=headless,
            )
        finally:
            cleanup_element_future(element_future)

def run_install_check():
    ensure_dirs()
    mapping = load_mapping_table()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto("data:text/html,<title>box-install-check</title>")
            if page.title() != "box-install-check":
                raise RuntimeError("浏览器安装检查失败。")
        finally:
            browser.close()
    log("安装检查", f"通过：映射 {len(mapping)} 条，浏览器可启动，数据目录 {BASE_DIR}")

def bilibili_login(update_bili_ids=False, update_break_data=False):
    ensure_dirs()
    had_existing_profile = USER_DATA_DIR.exists() and any(USER_DATA_DIR.iterdir())
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=browser_headless(),
            viewport=VIEWPORT,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            args=[f"--window-size={VIEWPORT['width']},{VIEWPORT['height']}"],
        )
        page = get_working_page(context)
        avatar_roles = {}
        if update_bili_ids:
            def collect_avatar_roles(response):
                if "/game/player/tools/fever/role/list" not in response.url:
                    return
                try:
                    payload = response.json()
                    for role in payload.get("data", {}).get("role_list", []):
                        if role.get("role_icon") and role.get("role_id") is not None:
                            avatar_roles[str(role["role_id"])] = role
                except Exception as exc:
                    log("头像匹配", f"读取 B 站圆形头像数据失败: {exc}")

            page.on("response", collect_avatar_roles)
        popup = None
        qr_path = None
        hbr_ids = None
        hbr_break_rows = None
        try:
            load_auth_state(context, had_existing_profile)
            log("浏览器", "正在检查现有登录态...")
            if is_logged_in(context, verbose=True):
                log("流程", "检测到有效登录态，跳过扫码登录。")
                open_hbr_page(page)
                hbr_ids = run_hbr_update(page, enabled=update_bili_ids)
                hbr_break_rows = run_hbr_break_update(page, enabled=update_break_data)
                return {"ids": hbr_ids, "break_rows": hbr_break_rows, "avatar_roles": avatar_roles}
            open_login_page(page)
            try:
                qr_path = capture_qr_image(page)
            except Exception:
                save_debug_screenshot(page, "qr_capture_error")
                raise
            popup = QRCodePopup(qr_path)
            popup.open()
            log("二维码", "二维码窗口已弹出，请扫码。")
            try:
                wait_for_login_success(context, page, popup)
            except Exception:
                save_debug_screenshot(page, "login_wait_error")
                raise
            save_auth_state(context)
            try:
                open_hbr_page(page)
                hbr_ids = run_hbr_update(page, enabled=update_bili_ids)
                hbr_break_rows = run_hbr_break_update(page, enabled=update_break_data)
            except Exception:
                save_debug_screenshot(page, "hbr_page_error")
                raise
            log("流程", "登录流程执行完成。")
            return {"ids": hbr_ids, "break_rows": hbr_break_rows, "avatar_roles": avatar_roles}
        except Exception as exc:
            log("错误", str(exc))
            try:
                save_debug_screenshot(page, "login_page_error")
            except Exception:
                log("调试截图", "当前页面无法保存调试截图。")
            raise
        finally:
            if popup is not None:
                popup.close()
            if qr_path and Path(qr_path).exists():
                try:
                    Path(qr_path).unlink()
                except OSError:
                    pass
            context.close()

def parse_args():
    parser = argparse.ArgumentParser(description="B 站 HBR 登录与可选数据抓取工具")
    parser.add_argument(
        "--check-install",
        action="store_true",
        help="离线检查安装版的映射表和浏览器能否正常使用",
    )
    parser.add_argument(
        "--sync-box",
        action="store_true",
        help="从 B站抓取全量 ID 与突破数据，更新映射表后同步到 BOX 图网站，再进入预览/下载流程",
    )
    parser.add_argument(
        "--box-initial-shot",
        action="store_true",
        help="仅打开 BOX 图网站并截图初始状态",
    )
    parser.add_argument(
        "--box-preview-download",
        action="store_true",
        help="仅打开 BOX 图网站，先弹出预览窗口，再决定是否下载",
    )
    parser.add_argument(
        "--preview-box-json",
        action="store_true",
        help="读取本地 box写入数据.json 并直接进入 BOX 预览/下载流程",
    )
    parser.add_argument(
        "--update-bili-ids",
        action="store_true",
        help="进入 HBR 页面后抓取并保存最新 B站 SS/SSR ID 列表",
    )
    parser.add_argument(
        "--update-break-data",
        action="store_true",
        help="进入 HBR 档案页后抓取并保存最新 B站 SS/SSR 突破数据",
    )
    parser.add_argument(
        "--update-mapping",
        action="store_true",
        help="抓取最新 B站 SS/SSR ID 并更新映射，未知前缀时可选择头像匹配",
    )
    parser.add_argument(
        "--generate-box-write-data",
        action="store_true",
        help="使用本地映射表和突破数据文件生成 box写入数据.json",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="直接打开主界面",
    )
    return parser.parse_args()
if __name__ == "__main__":
    configure_stdio()
    args = parse_args()
    if args.check_install:
        run_install_check()
    elif args.sync_box:
        run_full_box_sync()
    elif args.box_preview_download:
        run_box_preview_download()
    elif args.preview_box_json:
        run_box_preview_from_saved_data()
    elif args.box_initial_shot:
        run_box_initial_shot()
    elif args.update_mapping:
        run_mapping_update()
    elif args.generate_box_write_data:
        run_generate_box_write_data_from_files()
    elif args.gui:
        launch_main_window()
    elif args.update_bili_ids or args.update_break_data:
        bilibili_login(
            update_bili_ids=args.update_bili_ids,
            update_break_data=args.update_break_data,
        )
    else:
        launch_main_window()
