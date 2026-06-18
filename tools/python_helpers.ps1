$script:ToolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:ProjectRoot = Split-Path -Parent $script:ToolsDir

function Resolve-Python {
    param(
        [switch]$Windowed
    )

    $candidateFiles = @()
    if ($Windowed) {
        $candidateFiles += Join-Path $script:ProjectRoot ".venv\Scripts\pythonw.exe"
    }
    $candidateFiles += Join-Path $script:ProjectRoot ".venv\Scripts\python.exe"

    $localPythonPathFile = Join-Path $script:ProjectRoot ".python-path"
    if (Test-Path -LiteralPath $localPythonPathFile) {
        $localPythonPath = (Get-Content -LiteralPath $localPythonPathFile -TotalCount 1).Trim()
        if ($localPythonPath) {
            $candidateFiles += $localPythonPath
        }
    }

    if ($Windowed) {
        $envPythonw = [Environment]::GetEnvironmentVariable("PYTHONW_EXE")
        if ($envPythonw) {
            $candidateFiles += $envPythonw
        }
    }

    $envPython = [Environment]::GetEnvironmentVariable("PYTHON_EXE")
    if ($envPython) {
        $candidateFiles += $envPython
    }

    foreach ($path in $candidateFiles) {
        if (Test-Path -LiteralPath $path) {
            return [pscustomobject]@{
                File = $path
                Args = @()
            }
        }
    }

    $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return [pscustomobject]@{
            File = $pyLauncher.Source
            Args = @("-3")
        }
    }

    if ($Windowed) {
        $pythonw = Get-Command "pythonw" -ErrorAction SilentlyContinue
        if ($pythonw) {
            return [pscustomobject]@{
                File = $pythonw.Source
                Args = @()
            }
        }
    }

    $python = Get-Command "python" -ErrorAction SilentlyContinue
    if ($python) {
        return [pscustomobject]@{
            File = $python.Source
            Args = @()
        }
    }

    throw "Python 3 was not found. Install Python 3 or create .venv in the project root."
}

function Invoke-ResolvedPython {
    param(
        [Parameter(Mandatory = $true)]$Python,
        [string[]]$Arguments = @()
    )

    & $Python.File @($Python.Args + $Arguments)
    $script:ResolvedPythonExitCode = $LASTEXITCODE
}
