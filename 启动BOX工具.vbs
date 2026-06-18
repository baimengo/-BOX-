Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = fso.BuildPath(baseDir, "main.py")
runnerPath = fso.BuildPath(baseDir, "tools\run_python.ps1")

shell.CurrentDirectory = baseDir
shell.Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & runnerPath & """ -Script """ & scriptPath & """ -Windowed", 0, False
