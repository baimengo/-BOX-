# 红烧box

一个用于抓取 B 站 HBR 数据、维护映射表，并生成/预览 BOX 图的 Windows 桌面小工具。

## 功能

- 扫码登录 B 站并抓取 HBR SS/SSR 数据。
- 维护 `映射表(泳装二六版本).txt`。
- 生成 `box写入数据.json` 并写入 BOX 网站预览/导出。
- 提供 Tkinter 图形界面和命令行参数。

## 环境与依赖

需要 Windows + Python 3。

安装 Python 依赖：

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

如果使用 Python Launcher，也可以写成：

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m playwright install chromium
```

## 运行

双击：

```text
启动BOX工具.cmd
```

调试时可双击：

```text
启动BOX工具_调试.cmd
```

也可以手动运行：

```powershell
python main.py
```

## 常用命令

```powershell
python main.py --sync-box
python main.py --update-mapping
python main.py --generate-box-write-data
python main.py --preview-box-json
```

## 不会上传的本地文件

`.gitignore` 已排除这些内容：

- `bilibili_user_data/`
- `bilibili_storage_state.json`
- `bilibili_cookies.json`
- `debug/`
- `映射表历史/`
- 运行时生成的个人数据文件

示例数据以 `.example` 文件保留，方便了解格式。
