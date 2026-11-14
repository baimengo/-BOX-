# 红烧box

用于抓取 B 站 HBR 数据、维护角色映射，并生成和预览 BOX 图的 Windows 桌面工具。

## 功能

- 扫码登录 B 站，抓取 SS/SSR 全量 ID 和已持有角色的突破数据。
- 一键同步时更新 `当前映射表.txt`；遇到未知前缀可选择头像匹配并确认。
- 生成原版 BOX 图；检测到国服 PC 客户端数据时，并行生成按属性分类的 BOX 图，可在预览窗口切换和分别下载。
- 可在高级功能中选择运行时是否显示浏览器窗口。

## 文件结构

- `main.py`：统一入口，供启动脚本和命令行使用。
- `红烧box.py`：主界面与同步流程。
- `avatar_mapping.py`：头像匹配模块。
- `element_box.py`：PC 客户端数据导入与属性 BOX 图模块。
- `runtime_paths.py`：安装版的数据目录和随包浏览器路径。
- `当前映射表.txt`：随包提供的通用 ID 映射，不含登录信息。
- `启动BOX工具.cmd`、`启动BOX工具_调试.cmd`、`启动BOX工具.vbs`：Windows 启动入口。

## Windows 安装包

运行 `红烧box-Setup-1.0.0.exe` 即可安装。发布时应将此文件作为 GitHub Release 附件提供。安装包内含 Python 依赖和 Playwright Chromium，使用程序不需要配置 Python 环境。开始菜单中的“红烧box”可直接启动程序。

安装版把映射表、登录态、缓存和输出保存在 `%LOCALAPPDATA%\红烧box`；卸载程序不会自动删除这些个人数据。安装后也可以运行 `红烧box.exe --check-install`，离线检查映射表和浏览器是否可用。

## 从源码运行

需要 Windows 和 Python 3。下载仓库 ZIP 并解压后，在文件夹中安装依赖：

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

双击 `启动BOX工具.cmd` 打开图形界面；需要查看控制台日志时使用 `启动BOX工具_调试.cmd`。启动脚本会寻找文件夹内的 `.venv`、Python Launcher 或系统 Python，无需修改脚本中的绝对路径。

属性 BOX 图默认读取 `%USERPROFILE%\AppData\LocalLow\bilibili\HeavenBurnsRed\_bcdb0_`。若游戏数据位于别处，可设置环境变量 `HBR_PC_DATA_DIR` 指向该目录。

## 常用命令

```powershell
python main.py --sync-box
python main.py --update-mapping
python main.py --generate-box-write-data
python main.py --preview-box-json
```

## 数据格式

- 映射表每行形如 `1001103: 1:31a-1-1`。
- 突破列表每行形如 `1001103:4`，只记录已持有的角色。
- `box写入数据.json` 以 BOX 键为键；`-1` 表示未持有，`0` 表示已持有但零突破，正数表示突破等级。

## 本地文件

`.gitignore` 排除登录态、浏览器缓存、头像缓存、调试截图、输出图片和运行时生成的数据文件。仓库里的 `.example` 文件仅展示文件格式，不会被程序当作真实账号数据读取。

## 构建安装包

在 Windows 构建机上安装 Inno Setup 6，并运行：

```powershell
python -m pip install -r requirements-build.txt
python -m playwright install chromium
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_installer.ps1
```

构建脚本先打包 Python 与 Chromium，运行离线检查，再生成同级 `红烧box_构建产物\release` 文件夹中的安装包。编译器不在默认位置时，可用 `-IsccPath` 指定 `ISCC.exe`。

## 更新 GitHub 仓库

双击 `一键更新到GitHub.cmd`。脚本使用已安装的 Git 和 GitHub CLI，准备新版源码和安装包，显示变更及当前 GitHub 账号，输入 `YES` 后更新原仓库并上传 Release 附件。首次使用时需要在浏览器授权 GitHub CLI；脚本不会自动安装软件或运行 BOX 安装包。

只预览、不更新时运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\update_github.ps1 -DryRun
```

脚本默认选取同级 `红烧box_构建产物\release` 中最近生成的安装包，也可用 `-Version 1.0.1` 指定。更新其他版本前，先用构建脚本的 `-ReleaseVersion 1.0.1` 生成对应安装包。临时网络错误会重试，失败时窗口保留提示，具体命令和原始错误写入 `%TEMP%\box-github-update-last-error.log`。
