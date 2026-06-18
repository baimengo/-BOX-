param(
    [Parameter(Mandatory = $true)]
    [string]$Script,

    [switch]$Windowed,

    [string]$ArgsText = "",

    [string[]]$ScriptArgs = @()
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\python_helpers.ps1"

if ($ArgsText) {
    $parsedArgs = [regex]::Matches($ArgsText, '("[^"]*"|''[^'']*''|\S+)') | ForEach-Object {
        $_.Value.Trim('"', "'")
    }
    $ScriptArgs = @($ScriptArgs + $parsedArgs)
}

$python = Resolve-Python -Windowed:$Windowed
Invoke-ResolvedPython -Python $python -Arguments (@($Script) + $ScriptArgs)
exit $script:ResolvedPythonExitCode
