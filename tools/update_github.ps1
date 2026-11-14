param(
    [string]$Version = "",
    [string]$InstallerPath = "",
    [string]$RepositoryUrl = "https://github.com/baimengo/-BOX-.git",
    [switch]$DryRun,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$script:UpdateStage = "检查运行条件"
$script:UpdateErrorLog = Join-Path ([System.IO.Path]::GetTempPath()) "box-github-update-last-error.log"
trap {
    $failure = $_
    $detail = "GitHub 更新失败`r`n阶段：$script:UpdateStage`r`n原因：$($failure.Exception.Message)`r`n位置：$($failure.InvocationInfo.PositionMessage)"
    Write-Host "`n更新失败（$script:UpdateStage）：$($failure.Exception.Message)" -ForegroundColor Red
    try {
        [System.IO.File]::WriteAllText($script:UpdateErrorLog, $detail, [System.Text.Encoding]::UTF8)
        Write-Host "错误详情已保存：$script:UpdateErrorLog"
    } catch {
        Write-Host "无法保存错误日志，请保留窗口中的错误信息。"
    }
    exit 1
}

$repository = "baimengo/-BOX-"
$officialUrl = "https://github.com/$repository.git"
$sourceRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments, [switch]$Interactive)
    if ($Interactive) {
        & $Command @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Command $($Arguments -join ' ') 执行失败，退出码：$LASTEXITCODE。请查看窗口中的登录提示。"
        }
        return
    }
    $result = Invoke-Captured -Command $Command -Arguments $Arguments
    $lines = @($result.Output | ForEach-Object { [string]$_ })
    $lines | Write-Output
    if ($result.ExitCode -ne 0) {
        throw "$Command $($Arguments -join ' ') 执行失败，退出码：$($result.ExitCode)`r`n$($lines -join "`r`n")"
    }
}

function Invoke-Captured {
    param([string]$Command, [string[]]$Arguments)
    # PowerShell 5.1 turns redirected native stderr into ErrorRecords.
    # Expected failures, such as "not logged in", must be checked by exit code.
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $captured = @(& $Command @Arguments 2>&1)
        $nativeExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    return [pscustomobject]@{ ExitCode = $nativeExitCode; Output = $captured }
}

function Invoke-GitNetwork {
    param([string]$GitPath, [string[]]$Arguments, [string]$RetryDirectory = "")
    if ($RetryDirectory) {
        $allowedRoot = [System.IO.Path]::GetFullPath((Join-Path ([System.IO.Path]::GetTempPath()) "box-github-update"))
        $RetryDirectory = [System.IO.Path]::GetFullPath($RetryDirectory)
        if (-not $RetryDirectory.StartsWith($allowedRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "重试目录不在本脚本的临时目录内。"
        }
    }
    $transientError = '(?i)could not resolve host|failed to connect|connection.*(reset|timed out|closed)|timed out|SSL_(connect|read|write)|TLS|RPC failed|unexpected disconnect|HTTP (500|502|503|504)|requested URL returned error: (500|502|503|504)'
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $result = Invoke-Captured -Command $GitPath -Arguments $Arguments
        $lines = @($result.Output | ForEach-Object { [string]$_ })
        $lines | Write-Output
        if ($result.ExitCode -eq 0) { return }
        $detail = $lines -join "`r`n"
        if ($attempt -lt 3 -and $detail -match $transientError) {
            if ($RetryDirectory -and (Test-Path -LiteralPath $RetryDirectory)) {
                Remove-Item -LiteralPath $RetryDirectory -Recurse -Force
            }
            Write-Host "连接 GitHub 遇到临时网络错误，正在重试（$attempt/3）……"
            Start-Sleep -Seconds ($attempt * 2)
        } else {
            throw "$GitPath $($Arguments -join ' ') 执行失败，退出码：$($result.ExitCode)`r`n$detail"
        }
    }
}

function Find-Gh {
    $command = Get-Command gh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    $candidates = @(
        (Join-Path $env:ProgramFiles "GitHub CLI\gh.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\GitHub CLI\gh.exe"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\gh.exe")
    )
    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} "GitHub CLI\gh.exe"
    }
    return $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}

if (-not $DryRun -and $RepositoryUrl -ne $officialUrl) {
    throw "自定义仓库地址仅可用于 -DryRun，正式更新固定为 $officialUrl。"
}
$git = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $git) { throw "未找到 Git。请先安装 Git for Windows。" }
$gh = $null
if (-not $DryRun) {
    $gh = Find-Gh
    if (-not $gh) {
        throw "未找到 GitHub CLI（gh）。请先手动安装 GitHub CLI 后重试；更新脚本不会自动安装软件。"
    }
    Write-Host "使用已安装的 GitHub CLI：$gh"
}

if (-not $InstallerPath) {
    $releaseDir = Join-Path (Split-Path -Parent $sourceRoot) "红烧box_构建产物\release"
    if (-not (Test-Path -LiteralPath $releaseDir -PathType Container)) {
        throw "未找到安装包目录：$releaseDir"
    }
    if ($Version) {
        $InstallerPath = Join-Path $releaseDir "红烧box-Setup-$Version.exe"
    } else {
        $latest = Get-ChildItem -LiteralPath $releaseDir -Filter "红烧box-Setup-*.exe" -File |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $latest) { throw "安装包目录中没有红烧box-Setup-*.exe。" }
        $InstallerPath = $latest.FullName
    }
}
$InstallerPath = [System.IO.Path]::GetFullPath($InstallerPath)
$installer = Get-Item -LiteralPath $InstallerPath -ErrorAction Stop
if ($installer.PSIsContainer -or $installer.Name -notmatch '^红烧box-Setup-(.+)\.exe$') {
    throw "安装包文件名应为红烧box-Setup-版本号.exe。"
}
$fileVersion = $Matches[1]
if (-not $Version) { $Version = $fileVersion }
if ($Version -ne $fileVersion -or $Version -notmatch '^\d+\.\d+\.\d+(?:[-.][0-9A-Za-z]+)*$') {
    throw "版本号与安装包文件名不一致，或格式无效：$Version"
}
if ($installer.Length -le 0 -or $installer.Length -ge 2GB) {
    throw "安装包必须非空且小于 2 GiB。"
}
$tag = "v$Version"
$sha256 = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()

# Keep credentials, browser profiles, and personal BOX data outside this list.
$updateFiles = @(
    ".gitignore",
    "README.md",
    "avatar_mapping.py",
    "box写入数据.example.json",
    "b站ss_ssr_id列表.example.txt",
    "b站ss_ssr突破列表.example.txt",
    "element_box.py",
    "main.py",
    "requirements-build.txt",
    "requirements.txt",
    "runtime_paths.py",
    "start_BOX_tool.cmd",
    "一键更新到GitHub.cmd",
    "启动BOX工具.cmd",
    "启动BOX工具.vbs",
    "启动BOX工具_调试.cmd",
    "当前映射表.txt",
    "红烧box.py",
    "installer/启动红烧box.vbs",
    "installer/红烧box.iss",
    "scripts/box抓取代码.txt",
    "scripts/b站全id抓取代码.txt",
    "tests/test_installer_runtime.py",
    "tools/build_installer.ps1",
    "tools/update_github.ps1",
    "tools/python_helpers.ps1",
    "tools/run_python.ps1"
)
foreach ($relative in $updateFiles) {
    $source = Join-Path $sourceRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "更新清单中的文件不存在：$source"
    }
}

$tempRoot = [System.IO.Path]::GetFullPath((Join-Path ([System.IO.Path]::GetTempPath()) "box-github-update"))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$checkout = [System.IO.Path]::GetFullPath((Join-Path $tempRoot ([guid]::NewGuid().ToString("N"))))
if (-not $checkout.StartsWith($tempRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "临时目录路径异常。"
}

try {
    $script:UpdateStage = "检出原仓库并准备变更"
    Write-Host "检出原仓库最新 main：$RepositoryUrl"
    Invoke-GitNetwork -GitPath $git.Source -Arguments @("clone", "--depth", "1", "--single-branch", "--branch", "main", $RepositoryUrl, $checkout) -RetryDirectory $checkout
    Invoke-Checked -Command $git.Source -Arguments @("-C", $checkout, "config", "core.quotepath", "false")
    Invoke-Checked -Command $git.Source -Arguments @("-C", $checkout, "config", "core.safecrlf", "false")
    foreach ($relative in $updateFiles) {
        $destination = Join-Path $checkout $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $sourceRoot $relative) -Destination $destination -Force
    }
    $obsoleteFiles = @("映射表(泳装二六版本).txt", "一键发布到GitHub.cmd", "tools/publish_github.ps1")
    foreach ($obsolete in $obsoleteFiles) {
        if (Test-Path -LiteralPath (Join-Path $checkout $obsolete) -PathType Leaf) {
            Invoke-Checked -Command $git.Source -Arguments @("-C", $checkout, "rm", "--", $obsolete)
        }
    }
    Invoke-Checked -Command $git.Source -Arguments (@("-C", $checkout, "add", "-A", "--") + $updateFiles)
    Invoke-Checked -Command $git.Source -Arguments @("-C", $checkout, "diff", "--cached", "--check")
    & $git.Source -C $checkout diff --cached --quiet
    $diffCode = $LASTEXITCODE
    if ($diffCode -gt 1) { throw "无法检查待更新的源码差异。" }
    $hasChanges = $diffCode -eq 1
    $head = (& $git.Source -C $checkout rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "无法读取 main 提交。" }

    $tagRef = "refs/tags/$tag"
    $tagLines = @(& $git.Source -C $checkout ls-remote --tags origin $tagRef "$tagRef^{}")
    if ($LASTEXITCODE -ne 0) { throw "无法检查远程版本标签。" }
    $tagCommit = ""
    foreach ($line in $tagLines) {
        if ($line -match '^([0-9a-f]{40,64})\s+(.+)$') {
            if ($Matches[2] -eq "$tagRef^{}") { $tagCommit = $Matches[1]; break }
            if ($Matches[2] -eq $tagRef) { $tagCommit = $Matches[1] }
        }
    }
    if ($tagCommit -and ($hasChanges -or $tagCommit -ne $head)) {
        throw "远程标签 $tag 已用于不同源码。请先构建新版本安装包。"
    }

    Write-Host "`n版本：$tag"
    Write-Host "待上传安装包：$InstallerPath"
    Write-Host "大小：$([math]::Round($installer.Length / 1MB, 1)) MiB"
    Write-Host "SHA256：$sha256"
    Write-Host "`n待提交的源码差异："
    if ($hasChanges) {
        Invoke-Checked -Command $git.Source -Arguments @("-C", $checkout, "diff", "--cached", "--no-renames", "--name-status")
    } else {
        Write-Host "无；使用远程 main 的当前提交。"
    }
    if ($DryRun) {
        Write-Host "`n预览完成。未提交、推送或创建 Release。"
        return
    }

    $script:UpdateStage = "检查 GitHub 登录"
    $authStatus = Invoke-Captured -Command $gh -Arguments @("auth", "status", "--hostname", "github.com")
    if ($authStatus.ExitCode -ne 0) {
        Write-Host "请在浏览器完成 GitHub 登录。"
        Invoke-Checked -Command $gh -Arguments @("auth", "login", "--hostname", "github.com", "--web", "--git-protocol", "https") -Interactive
    }
    $authUser = Invoke-Checked -Command $gh -Arguments @("api", "user", "--jq", ".login")
    if (-not $authUser) { throw "无法确认当前 GitHub 登录账号。" }
    $authUser = $authUser.Trim()
    Write-Host "当前 GitHub 账号：$authUser"
    if (-not $Yes) {
        $answer = Read-Host "确认使用此账号更新仓库并发布 $tag？输入 YES 继续"
        if ($answer -cne "YES") { Write-Host "已取消更新。"; return }
    }
    Invoke-Checked -Command $gh -Arguments @("auth", "setup-git", "--hostname", "github.com")

    if ($hasChanges) {
        $script:UpdateStage = "提交源码"
        $authorName = & $git.Source -C $checkout config user.name
        $authorEmail = & $git.Source -C $checkout config user.email
        if (-not $authorName -or -not $authorEmail) {
            throw "Git 提交身份未配置。请先设置 git config --global user.name 和 user.email。"
        }
        Invoke-Checked -Command $git.Source -Arguments @("-C", $checkout, "commit", "-m", "Release $tag")
        $script:UpdateStage = "推送源码"
        Invoke-GitNetwork -GitPath $git.Source -Arguments @("-C", $checkout, "push", "origin", "HEAD:main")
        $head = (& $git.Source -C $checkout rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0) { throw "无法读取新提交。" }
    }

    $script:UpdateStage = "更新 Release 安装包"
    $releaseResult = Invoke-Captured -Command $gh -Arguments @("api", "repos/$repository/releases/tags/$tag")
    $releaseResponse = $releaseResult.Output
    $releaseExists = $releaseResult.ExitCode -eq 0
    if (-not $releaseExists -and (($releaseResponse | Out-String) -notmatch '(?i)404|not found')) {
        throw "检查 GitHub Release 失败：$($releaseResponse | Out-String)"
    }
    if ($releaseExists) {
        $release = ($releaseResponse -join "`n") | ConvertFrom-Json
        $existingAsset = $release.assets | Where-Object { $_.name -eq $installer.Name } | Select-Object -First 1
        if ($existingAsset) {
            if ($existingAsset.digest -and $existingAsset.digest -ne "sha256:$sha256") {
                throw "Release 中已有同名但 SHA256 不同的安装包，请使用新版本号。"
            }
            if ($existingAsset.size -ne $installer.Length) { throw "Release 中的同名安装包大小不同。" }
            Write-Host "Release 已有相同安装包。"
        } else {
            Invoke-Checked -Command $gh -Arguments @("release", "upload", $tag, $InstallerPath, "--repo", $repository)
        }
        if ($release.draft) {
            Invoke-Checked -Command $gh -Arguments @("release", "edit", $tag, "--repo", $repository, "--draft=false")
        }
    } else {
        $notes = "Windows 安装包：双击安装，无需配置 Python 环境。源码可从本 Release 下载。"
        Invoke-Checked -Command $gh -Arguments @("release", "create", $tag, $InstallerPath, "--repo", $repository, "--target", $head, "--title", "红烧box $tag", "--notes", $notes)
    }
    $verified = (Invoke-Checked -Command $gh -Arguments @("api", "repos/$repository/releases/tags/$tag") | ConvertFrom-Json)
    $asset = $verified.assets | Where-Object { $_.name -eq $installer.Name } | Select-Object -First 1
    if (-not $asset -or $asset.size -ne $installer.Length -or ($asset.digest -and $asset.digest -ne "sha256:$sha256")) {
        throw "发布后校验失败：GitHub 上的安装包缺失、大小或 SHA256 不一致。"
    }
    Write-Host "更新并发布成功：$($verified.html_url)"
} finally {
    if (Test-Path -LiteralPath $checkout) {
        $safeCheckout = [System.IO.Path]::GetFullPath($checkout)
        if ($safeCheckout.StartsWith($tempRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $safeCheckout -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
