"""Match Bilibili role_icon portraits to BOX card images in the experiment copy."""

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import math
import re
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageOps, ImageTk
from runtime_paths import DATA_DIR


BOX_IMAGE_PATTERN = re.compile(r"\bvar\s+urls\s*=\s*(\{.*?\})\s*;", re.S)
BOX_KEY_PATTERN = re.compile(r"^[\w]+(?:-[\w]+)+$")
BOX_DATA_HEADER_PATTERN = re.compile(r"data:image/[a-z0-9.+-]+;base64", re.I)
AVATAR_CACHE_DIR = DATA_DIR / "avatar_cache"
MAX_AVATAR_DISTANCE = 12.0
AUTO_MATCH_DISTANCE = 5.0
AUTO_ACCEPT_DISTANCE = 3.0


class AvatarMatchCancelled(Exception):
    pass


def unknown_prefixes(mapping, style_ids):
    known = {str(style_id)[:-2] for style_id in mapping}
    return sorted({str(style_id)[:-2] for style_id in style_ids
                   if str(style_id)[:-2] not in known})


def parse_box_images(html):
    match = BOX_IMAGE_PATTERN.search(html)
    if not match:
        raise RuntimeError("BOX 页面没有找到卡片头像数据。")
    # The site's JavaScript object is JSON apart from its trailing comma.
    values = json.loads(re.sub(r",\s*}", "}", match.group(1)))
    images = {}
    for key, source in values.items():
        if not BOX_KEY_PATTERN.fullmatch(key) or not isinstance(source, str):
            continue
        header, separator, payload = source.partition(",")
        if not separator or not BOX_DATA_HEADER_PATTERN.fullmatch(header):
            continue
        with Image.open(io.BytesIO(base64.b64decode(payload, validate=True))) as image:
            images[key] = image.copy()
    if not images:
        raise RuntimeError("BOX 页面没有可用的卡片头像。")
    return images


def download_box_images(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=45) as response:
        html = response.read().decode("utf-8")
    return parse_box_images(html)


def download_role_icon(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("B 站角色头像链接无效。")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://game.bilibili.com/"})
    with urlopen(request, timeout=30) as response:
        data = response.read()
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        return image.copy()


def _prepared_avatar(image, crop_fraction):
    image = image.convert("RGBA")
    width, height = image.size
    inset_x, inset_y = round(width * crop_fraction), round(height * crop_fraction)
    image = image.crop((inset_x, inset_y, width - inset_x, height - inset_y))
    background = Image.new("RGBA", image.size, "white")
    background.alpha_composite(image)
    return ImageOps.fit(background.convert("L"), (32, 32), method=Image.Resampling.LANCZOS)


def _perceptual_hash(image, crop_fraction):
    pixels = _prepared_avatar(image, crop_fraction).load()
    cosine = [[math.cos((2 * x + 1) * f * math.pi / 64) for x in range(32)] for f in range(8)]
    horizontal = [[sum(pixels[x, y] * cosine[f][x] for x in range(32)) for y in range(32)] for f in range(8)]
    coefficients = [sum(horizontal[u][y] * cosine[v][y] for y in range(32)) for u in range(8) for v in range(8)]
    median = sorted(coefficients[1:])[31]
    result = 0
    for coefficient in coefficients[1:]:
        result = (result << 1) | int(coefficient > median)
    return result


def avatar_fingerprint(image):
    return (_perceptual_hash(image, 0.15), _perceptual_hash(image, 0.0))


def _avatar_distance(first, second):
    center_distance = (first[0] ^ second[0]).bit_count()
    full_distance = (first[1] ^ second[1]).bit_count()
    return center_distance + 0.35 * full_distance


def _load_cached_role_icon(style_id, url, download):
    cache_name = hashlib.sha256(f"{style_id}:{url}".encode("utf-8")).hexdigest() + ".png"
    cache_path = AVATAR_CACHE_DIR / cache_name
    if cache_path.exists():
        try:
            with Image.open(cache_path) as image:
                image.load()
                return image.copy()
        except OSError:
            cache_path.unlink(missing_ok=True)
    image = download(url)
    AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    image.convert("RGBA").save(cache_path, format="PNG")
    return image.copy()


def load_role_images(avatar_roles, style_ids, download=download_role_icon):
    role_urls = {}
    for style_id in sorted({str(value) for value in style_ids}, key=int):
        role = avatar_roles.get(style_id)
        if not role or not role.get("role_icon"):
            raise RuntimeError(f"B站角色 {style_id} 缺少圆形头像，无法安全筛选 BOX 图片。")
        role_urls[style_id] = role["role_icon"]

    def load(item):
        style_id, url = item
        return style_id, _load_cached_role_icon(style_id, url, download)

    images = {}
    failures = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(load, item) for item in role_urls.items()]
        for future in futures:
            try:
                style_id, image = future.result()
                images[style_id] = image
            except Exception as exc:
                failures.append(str(exc))
    if failures:
        raise RuntimeError(f"下载或读取 B 站头像失败，未开始比对：{failures[0]}")
    return images


def filter_box_images_by_role_icons(box_images, role_images, eligible_ids, used_keys=(),
                                    max_score=MAX_AVATAR_DISTANCE, include_low_confidence=False):
    eligible = {str(style_id) for style_id in eligible_ids}
    used = set(used_keys)
    role_fingerprints = {
        style_id: avatar_fingerprint(image)
        for style_id, image in role_images.items()
    }
    eligible_fingerprints = [
        fingerprint for style_id, fingerprint in role_fingerprints.items()
        if style_id in eligible
    ]
    mapped_fingerprints = [
        fingerprint for style_id, fingerprint in role_fingerprints.items()
        if style_id not in eligible
    ]
    filtered = {}
    for key, image in box_images.items():
        if key in used:
            continue
        fingerprint = avatar_fingerprint(image)
        eligible_score = min(
            (_avatar_distance(fingerprint, candidate) for candidate in eligible_fingerprints),
            default=float("inf"),
        )
        mapped_score = min(
            (_avatar_distance(fingerprint, candidate) for candidate in mapped_fingerprints),
            default=float("inf"),
        )
        if eligible_score < mapped_score and (include_low_confidence or eligible_score <= max_score):
            filtered[key] = image
    return filtered


def rank_box_images(role_image, box_images, used_keys=(), expected_slot=None, stem=None,
                    max_score=None):
    target = avatar_fingerprint(role_image)
    used = set(used_keys)
    ranked = []
    for key, image in box_images.items():
        if key in used or (stem is not None and not key.startswith(stem)):
            continue
        if expected_slot is not None and not key.endswith(f"-{expected_slot}"):
            continue
        fingerprint = avatar_fingerprint(image)
        score = _avatar_distance(target, fingerprint)
        if max_score is None or score <= max_score:
            ranked.append({"key": key, "score": score})
    return sorted(ranked, key=lambda item: (item["score"], item["key"]))


def ask_match_permission(prefixes):
    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        return messagebox.askyesno(
            "发现未知角色前缀",
            "发现 B 站新角色前缀：" + "、".join(prefixes)
            + "\n\n是否使用养成助手的圆形头像与 BOX 卡片头像比对，查找映射？",
            parent=root,
        )
    finally:
        root.destroy()


def choose_box_image(style_id, role_name, role_image, ranked, box_images):
    if not ranked:
        return None
    root = tk.Tk()
    root.title("确认头像映射")
    root.geometry("620x450")
    root.minsize(540, 370)
    root.attributes("-topmost", True)
    result = {"key": None}
    outer = ttk.Frame(root, padding=12)
    outer.pack(fill="both", expand=True)
    if any(item["score"] > MAX_AVATAR_DISTANCE or item.get("manual_fallback") for item in ranked):
        ttk.Label(
            outer,
            text="差异分数只用于排序；低相似候选也会列出，请结合预览自行判断。",
        ).pack(anchor="w", pady=(0, 6))
    ttk.Label(outer, text=f"B 站 {style_id}  {role_name}", font=("Microsoft YaHei UI", 11)).pack(anchor="w")
    ttk.Label(outer, text="请选择与左侧圆形头像对应的 BOX 卡片：").pack(anchor="w", pady=(6, 10))
    body = ttk.Frame(outer)
    body.pack(fill="both", expand=True)
    left = ttk.Frame(body)
    left.pack(side="left", fill="y")
    role_photo = ImageTk.PhotoImage(ImageOps.contain(role_image.convert("RGBA"), (124, 124)))
    ttk.Label(left, image=role_photo).pack()
    ttk.Label(left, text="B 站 role_icon").pack(pady=(4, 0))
    middle = ttk.Frame(body)
    middle.pack(side="left", fill="both", expand=True, padx=12)
    listbox = tk.Listbox(middle, exportselection=False, font=("Consolas", 10))
    scrollbar = ttk.Scrollbar(middle, orient="vertical", command=listbox.yview)
    listbox.configure(yscrollcommand=scrollbar.set)
    listbox.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    for item in ranked:
        warning = "  需人工核对" if item["score"] > MAX_AVATAR_DISTANCE or item.get("manual_fallback") else ""
        listbox.insert("end", f"1:{item['key']}    差异 {item['score']:.1f}{warning}")
    right = ttk.Frame(body, width=130)
    right.pack(side="right", fill="y")
    preview = ttk.Label(right)
    preview.pack()
    preview_name = ttk.Label(right)
    preview_name.pack(pady=(4, 0))

    def on_select(_event=None):
        if not listbox.curselection():
            return
        key = ranked[listbox.curselection()[0]]["key"]
        photo = ImageTk.PhotoImage(ImageOps.contain(box_images[key].convert("RGBA"), (124, 124)))
        preview.configure(image=photo)
        preview.image = photo
        preview_name.configure(text="BOX 1:" + key)

    listbox.bind("<<ListboxSelect>>", on_select)
    if ranked[0]["score"] <= MAX_AVATAR_DISTANCE and not ranked[0].get("manual_fallback"):
        listbox.selection_set(0)
        on_select()

    def confirm():
        if listbox.curselection():
            result["key"] = ranked[listbox.curselection()[0]]["key"]
            root.destroy()

    buttons = ttk.Frame(outer)
    buttons.pack(fill="x", pady=(12, 0))
    ttk.Button(buttons, text="跳过当前", command=root.destroy).pack(side="right")
    ttk.Button(buttons, text="确认映射", command=confirm).pack(side="right", padx=(0, 8))
    root.mainloop()
    return result["key"]


def _review_order(matches, mode):
    if mode == "sequence":
        return list(matches)
    if mode == "difference":
        return sorted(matches, key=lambda style_id: matches[style_id]["score"], reverse=True)
    raise ValueError(f"Unknown review order: {mode}")


def review_avatar_matches(matches):
    automatically_accepted = {
        style_id: match["mapping_value"] for style_id, match in matches.items()
        if match["score"] < AUTO_ACCEPT_DISTANCE
    }
    matches = {
        style_id: match for style_id, match in matches.items()
        if style_id not in automatically_accepted
    }
    if not matches:
        return automatically_accepted
    root = tk.Tk()
    root.title("复核新增头像映射")
    root.geometry("720x600")
    root.minsize(580, 400)
    root.attributes("-topmost", True)
    result = {"accepted": automatically_accepted or None}
    selected = {}
    row_widgets = {}
    photos = []
    outer = ttk.Frame(root, padding=12)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text=f"新增配对 ({len(matches)})", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
    ttk.Label(outer, text="取消勾选错误配对，确认后写入映射表。左侧为 B 站头像，右侧为 BOX 头像。").pack(anchor="w", pady=(4, 4))
    ttk.Label(outer, text=f"差异小于 {AUTO_ACCEPT_DISTANCE:g} 的配对已自动确认，不在此处显示。").pack(anchor="w", pady=(0, 4))
    sort_controls = ttk.Frame(outer)
    sort_controls.pack(fill="x", pady=(0, 8))
    sort_mode = tk.StringVar(value="difference")

    body = ttk.Frame(outer)
    body.pack(fill="both", expand=True)
    canvas = tk.Canvas(body, highlightthickness=0)
    scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    rows = ttk.Frame(canvas)
    rows_window = canvas.create_window((0, 0), window=rows, anchor="nw")
    rows.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(rows_window, width=event.width))

    for style_id, match in matches.items():
        item_frame = ttk.Frame(rows)
        row_widgets[style_id] = item_frame
        row = ttk.Frame(item_frame, padding=(6, 8))
        row.pack(fill="x")
        keep = tk.BooleanVar(value=True)
        selected[style_id] = keep
        ttk.Checkbutton(row, text="保留", variable=keep).pack(side="left", padx=(0, 10))
        role_photo = ImageTk.PhotoImage(ImageOps.contain(match["role_image"].convert("RGBA"), (80, 80)))
        box_photo = ImageTk.PhotoImage(ImageOps.contain(match["box_image"].convert("RGBA"), (80, 80)))
        photos.extend((role_photo, box_photo))
        ttk.Label(row, image=role_photo).pack(side="left")
        ttk.Label(row, text="  ↔  ").pack(side="left")
        ttk.Label(row, image=box_photo).pack(side="left")
        details = ttk.Frame(row)
        details.pack(side="left", fill="x", expand=True, padx=(12, 0))
        ttk.Label(details, text=f"{style_id}  {match['role_name']}  →  {match['mapping_value']}").pack(anchor="w")
        source = "自动匹配" if match["automatic"] else "人工选择"
        ttk.Label(details, text=f"{source} · 差异 {match['score']:.1f}").pack(anchor="w", pady=(4, 0))
        ttk.Separator(item_frame).pack(fill="x")

    def reorder_rows():
        for item_frame in row_widgets.values():
            item_frame.pack_forget()
        for style_id in _review_order(matches, sort_mode.get()):
            row_widgets[style_id].pack(fill="x")
        canvas.yview_moveto(0)

    ttk.Label(sort_controls, text="排序：").pack(side="left")
    ttk.Radiobutton(sort_controls, text="差异从高到低（默认）", variable=sort_mode,
                    value="difference", command=reorder_rows).pack(side="left", padx=(0, 12))
    ttk.Radiobutton(sort_controls, text="原始配对顺序", variable=sort_mode,
                    value="sequence", command=reorder_rows).pack(side="left")
    reorder_rows()

    def confirm():
        result["accepted"] = {
            **automatically_accepted,
            **{
                style_id: match["mapping_value"]
                for style_id, match in matches.items()
                if selected[style_id].get()
            },
        }
        root.destroy()

    buttons = ttk.Frame(outer)
    buttons.pack(fill="x", pady=(10, 0))
    ttk.Button(buttons, text="确定并写入映射", command=confirm).pack(side="right")
    cancel_text = "跳过待复核配对" if automatically_accepted else "取消"
    ttk.Button(buttons, text=cancel_text, command=root.destroy).pack(side="right", padx=(0, 8))
    root.mainloop()
    return result["accepted"]


def resolve_unknown_styles(mapping, style_ids, avatar_roles, box_images, choose=choose_box_image,
                           download=download_role_icon, on_skip=None,
                           review_items=None):
    prefixes = unknown_prefixes(mapping, style_ids)
    used_keys = {value.removeprefix("1:") for value in mapping.values()}
    active_ids = {str(value) for value in style_ids}
    role_images = load_role_images(avatar_roles, active_ids, download=download)
    eligible_ids = active_ids - {str(style_id) for style_id in mapping}
    available_box_images = filter_box_images_by_role_icons(
        box_images, role_images, eligible_ids, used_keys=used_keys,
        include_low_confidence=True,
    )
    additions = {}
    for prefix in prefixes:
        ids = sorted({str(value) for value in style_ids if str(value).startswith(prefix)
                      and str(value)[:-2] == prefix}, key=int)
        stem = None
        for slot, style_id in enumerate(ids, start=1):
            role = avatar_roles.get(style_id)
            role_image = role_images[style_id]
            ranked = rank_box_images(
                role_image, available_box_images, used_keys,
                expected_slot=slot, stem=stem,
            )
            candidate_images = available_box_images
            if not ranked:
                ranked = rank_box_images(role_image, available_box_images, used_keys)
                for item in ranked:
                    item["manual_fallback"] = True
            if not ranked:
                candidate_images = {
                    key: image for key, image in box_images.items()
                    if key not in used_keys
                }
                ranked = rank_box_images(role_image, candidate_images, used_keys)
                for item in ranked:
                    item["manual_fallback"] = True
            if not ranked:
                raise RuntimeError(
                    f"角色 {style_id} 没有剩余 BOX 图片可供人工判断；本轮新增映射未保存。"
                )
            close_matches = [item for item in ranked if item["score"] <= AUTO_MATCH_DISTANCE]
            automatic = ranked[0]["score"] < AUTO_ACCEPT_DISTANCE or (
                len(close_matches) == 1 and not close_matches[0].get("manual_fallback")
            )
            key = ranked[0]["key"] if automatic else choose(
                style_id, role.get("role_name", ""), role_image, ranked, candidate_images,
            )
            if key is None:
                if on_skip:
                    on_skip(style_id)
                continue
            selected = next((item for item in ranked if item["key"] == key), None)
            if selected is None:
                raise RuntimeError(f"BOX 卡片 {key} 不在可选列表，映射表未保存。")
            selected_stem = key.rsplit("-", 1)[0] + "-"
            if stem is not None and selected_stem != stem:
                raise RuntimeError(f"角色前缀 {prefix} 对应的 BOX 前缀不一致，映射表未保存。")
            stem = selected_stem
            used_keys.add(key)
            additions[style_id] = "1:" + key
            if review_items is not None:
                review_items[style_id] = {
                    "role_name": role.get("role_name", ""),
                    "role_image": role_image,
                    "box_image": candidate_images[key],
                    "mapping_value": additions[style_id],
                    "score": selected["score"],
                    "automatic": automatic,
                }
    return additions
