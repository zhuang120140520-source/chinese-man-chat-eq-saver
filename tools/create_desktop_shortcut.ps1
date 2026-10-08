param([Parameter(Mandatory = $true)][string]$Executable)
$ErrorActionPreference = 'Stop'
$exePath = (Get-Item -LiteralPath $Executable).FullName
$desktopPath = [Environment]::GetFolderPath('DesktopDirectory')
if (-not $desktopPath) { throw 'Desktop folder could not be resolved.' }
$shell = New-Object -ComObject WScript.Shell
$linkPath = Join-Path $desktopPath 'Chinese Man 聊天情商拯救器.lnk'
if (Test-Path -LiteralPath $linkPath) {
    $existing = $shell.CreateShortcut($linkPath)
    if ([IO.Path]::GetFileName($existing.TargetPath) -ne 'jev-partner-chat.exe') {
        $linkPath = Join-Path $desktopPath 'Chinese Man 聊天情商拯救器-新版.lnk'
    }
}
$link = $shell.CreateShortcut($linkPath)
$link.TargetPath = $exePath
$link.WorkingDirectory = [IO.Path]::GetDirectoryName($exePath)
$link.IconLocation = $exePath + ',0'
$link.Description = 'Chinese Man 聊天情商拯救器聊天助手：点击按钮后才截图和生成回复'
$link.Save()
$saved = $shell.CreateShortcut($linkPath)
if ($saved.TargetPath -ne $exePath -or $saved.WorkingDirectory -ne [IO.Path]::GetDirectoryName($exePath)) {
    throw 'Shortcut verification failed.'
}
Write-Output $linkPath
# Replace only this project's previous shortcut after the new link is verified.
$legacyPath = Join-Path $desktopPath '嘴替小抄.lnk'
$workspaceRoot = [IO.Path]::GetDirectoryName([IO.Path]::GetDirectoryName($exePath))
$expectedLegacyTarget = Join-Path $workspaceRoot 'PartnerChat-Trial-0.6.0\jev-partner-chat.exe'
if (Test-Path -LiteralPath $legacyPath) {
    $legacy = $shell.CreateShortcut($legacyPath)
    if ($legacy.TargetPath -eq $expectedLegacyTarget) {
        Remove-Item -LiteralPath $legacyPath
    }
}
