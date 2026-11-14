param(
    [string]$Python = "python",
    [string]$IsccPath = "",
    [string]$BuildRoot = "",
    [string]$ReleaseVersion = "1.0.0"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $BuildRoot) {
    $BuildRoot = Join-Path (Split-Path -Parent $projectRoot) "红烧box_构建产物"
}
$BuildRoot = [System.IO.Path]::GetFullPath($BuildRoot)
$distPath = Join-Path $BuildRoot "dist"
$workPath = Join-Path $BuildRoot "build"
$specPath = Join-Path $BuildRoot "spec"
$outputPath = Join-Path $BuildRoot "release"

if (-not $IsccPath) {
    $isccCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    $candidates = @(
        (Join-Path $BuildRoot "InnoSetup\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    if ($isccCommand) { $candidates = @($isccCommand.Source) + $candidates }
    $IsccPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath)) {
    throw "未找到 Inno Setup 的 ISCC.exe。请安装 Inno Setup 6 或用 -IsccPath 指定路径。"
}

$manifestCode = "import json,pathlib,playwright; p=pathlib.Path(playwright.__file__).parent/'driver'/'package'/'browsers.json'; d=json.loads(p.read_text(encoding='utf-8')); print(json.dumps({b['name']:b['revision'] for b in d['browsers'] if b['name'] in ('chromium','chromium-headless-shell')}))"
$revisionsJson = & $Python -c $manifestCode
if ($LASTEXITCODE -ne 0) { throw "无法读取当前 Playwright 的浏览器版本。" }
$revisions = $revisionsJson | ConvertFrom-Json
$chromiumName = "chromium-$($revisions.chromium)"
$headlessName = "chromium_headless_shell-$($revisions.'chromium-headless-shell')"
$browserRoot = Join-Path $env:LOCALAPPDATA "ms-playwright"
$chromiumPath = Join-Path $browserRoot $chromiumName
$headlessPath = Join-Path $browserRoot $headlessName
foreach ($browserPath in @($chromiumPath, $headlessPath)) {
    if (-not (Test-Path -LiteralPath $browserPath)) {
        throw "缺少浏览器 $browserPath。请先运行：$Python -m playwright install chromium"
    }
}

foreach ($directory in @($BuildRoot, $distPath, $workPath, $specPath, $outputPath)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$browserPayloadRoot = Join-Path $BuildRoot "browser_payload"
foreach ($browser in @(
    @{ Source = $chromiumPath; Name = $chromiumName },
    @{ Source = $headlessPath; Name = $headlessName }
)) {
    $stagedPath = Join-Path $browserPayloadRoot $browser.Name
    New-Item -ItemType Directory -Path $stagedPath -Force | Out-Null
    & robocopy.exe $browser.Source $stagedPath /E /XF *.log *.tmp *.dmp /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "复制浏览器 $($browser.Name) 失败。" }
}
$stagedChromiumPath = Join-Path $browserPayloadRoot $chromiumName
$stagedHeadlessPath = Join-Path $browserPayloadRoot $headlessName

$pyinstallerArgs = @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console",
    "--contents-directory", "_internal", "--name", "红烧box",
    "--distpath", $distPath, "--workpath", $workPath, "--specpath", $specPath,
    "--collect-all", "playwright",
    "--add-data", "$(Join-Path $projectRoot '当前映射表.txt');.",
    "--add-data", "$stagedChromiumPath;ms-playwright/$chromiumName",
    "--add-data", "$stagedHeadlessPath;ms-playwright/$headlessName",
    (Join-Path $projectRoot "红烧box.py")
)
& $Python @pyinstallerArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败。" }

$bundlePath = Join-Path $distPath "红烧box"
$exePath = Join-Path $bundlePath "红烧box.exe"
if (-not (Test-Path -LiteralPath $exePath)) { throw "没有生成红烧box.exe。" }
foreach ($browserName in @($chromiumName, $headlessName)) {
    if (-not (Test-Path -LiteralPath (Join-Path $bundlePath "_internal\ms-playwright\$browserName"))) {
        throw "安装目录缺少浏览器 $browserName。"
    }
}

$smokeData = Join-Path $BuildRoot "smoke_data"
New-Item -ItemType Directory -Path $smokeData -Force | Out-Null
$previousLocalAppData = $env:LOCALAPPDATA
try {
    $env:LOCALAPPDATA = $smokeData
    & $exePath --check-install
    if ($LASTEXITCODE -ne 0) { throw "打包程序的离线安装检查失败。" }
} finally {
    $env:LOCALAPPDATA = $previousLocalAppData
}

$bundledBrowserRoot = Join-Path $bundlePath "_internal\ms-playwright"
$generatedLogs = @(Get-ChildItem -LiteralPath $bundledBrowserRoot -Recurse -File | Where-Object {
    $_.Extension -in @(".log", ".tmp", ".dmp")
})
foreach ($generatedLog in $generatedLogs) {
    if (-not $generatedLog.FullName.StartsWith($bundledBrowserRoot + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "浏览器日志不在预期构建目录内：$($generatedLog.FullName)"
    }
    Remove-Item -LiteralPath $generatedLog.FullName -Force
}

$issPath = Join-Path $projectRoot "installer\红烧box.iss"
& $IsccPath "/Qp" "/DSourceDir=$bundlePath" "/DReleaseVersion=$ReleaseVersion" "/O$outputPath" $issPath
if ($LASTEXITCODE -ne 0) { throw "Inno Setup 编译失败。" }

$installerPath = Join-Path $outputPath "红烧box-Setup-$ReleaseVersion.exe"
if (-not (Test-Path -LiteralPath $installerPath)) { throw "没有生成安装包 $installerPath。" }
Write-Output "安装包：$installerPath"
