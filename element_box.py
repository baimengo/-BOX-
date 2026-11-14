"""Create the element-sorted BOX PNG from the CN PC client's local data."""

import os
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright


STYLE_MANAGER_URL = "https://style.hbr.quest/cn"
GAME_DATA_RELATIVE_PATH = Path("AppData/LocalLow/bilibili/HeavenBurnsRed/_bcdb0_")


def find_game_data_folder():
    override = os.environ.get("HBR_PC_DATA_DIR")
    folder = Path(override).expanduser() if override else Path.home() / GAME_DATA_RELATIVE_PATH
    if not folder.is_dir():
        raise RuntimeError(f"未找到国服 PC 客户端数据目录：{folder}")
    if not any(folder.iterdir()):
        raise RuntimeError(f"国服 PC 客户端数据目录为空：{folder}")
    return folder


def download_element_box_image(browser, target_path, game_data_folder=None):
    """Use the site's own import and By element PNG export in a fresh browser context."""
    folder = Path(game_data_folder) if game_data_folder else find_game_data_folder()
    if not folder.is_dir():
        raise RuntimeError(f"PC 客户端数据目录不存在：{folder}")
    target = Path(target_path)
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        accept_downloads=True,
    )

    def block_writes(route):
        if route.request.method in ("GET", "HEAD"):
            route.continue_()
        else:
            route.abort()

    context.route("**/*", block_writes)
    page = context.new_page()
    page.set_default_timeout(45000)
    try:
        response = page.goto(STYLE_MANAGER_URL, wait_until="domcontentloaded", timeout=45000)
        if response is None or response.status >= 400:
            raise RuntimeError("属性 BOX 网站未能正常打开。")

        page.get_by_role("button", name="PC Client Import").first.click()
        with page.expect_file_chooser() as chooser_info:
            page.get_by_role("button", name="Choose the _bcdb0_ folder").click()
        chooser_info.value.set_files(str(folder), timeout=45000)
        page.get_by_role("button", name="Apply changes").click(timeout=90000)

        page.get_by_role("button", name="Share").first.click()
        page.get_by_role("menuitem", name="Box Image").click()
        page.get_by_role("button", name="By element").click()
        with page.expect_download(timeout=90000) as download_info:
            page.get_by_role("button", name="Download PNG").click()
        target.parent.mkdir(parents=True, exist_ok=True)
        download_info.value.save_as(str(target))
        with Image.open(target) as image:
            if image.format != "PNG" or min(image.size) < 100:
                raise RuntimeError("属性 BOX 网站返回的图片格式或尺寸不正确。")
            image.verify()
        return target
    finally:
        context.close()


def create_element_box_preview(headless=True):
    """Run the element-site browser independently and return a temporary PNG."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
        target = Path(temp_file.name)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            try:
                return download_element_box_image(browser, target)
            finally:
                browser.close()
    except Exception:
        target.unlink(missing_ok=True)
        raise
