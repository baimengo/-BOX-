Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = appDir
appExe = ChrW(&H7EA2) & ChrW(&H70E7) & "box.exe"
shell.Run """" & fso.BuildPath(appDir, appExe) & """", 0, False
