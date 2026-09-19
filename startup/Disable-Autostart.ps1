param([string]$ConfigFile=(Join-Path (Split-Path $PSScriptRoot -Parent) 'local-installation\config.json'),[switch]$KeepRunning)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Supervisor.Core.ps1')
$runtime=Get-StartupDirectory
$record=Join-Path $runtime 'autostart.json'
$task=$null
if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {
    $task=Get-ScheduledTask -TaskName 'SignalRGB Local Bridges' -ErrorAction SilentlyContinue
} elseif ((Test-Path -LiteralPath $record) -and (Get-Content -LiteralPath $record -Raw | ConvertFrom-Json).method -eq 'ScheduledTask') {
    throw 'Le module ScheduledTasks est indisponible ; la suppression de la tache ne peut pas etre confirmee.'
}
if ($task) {
    if (-not (@($task.Actions | Where-Object {$_.Arguments -like '*Start-Supervisor.ps1*'}).Count)) { throw 'La tache homonyme ne correspond pas a ce gestionnaire.' }
    Unregister-ScheduledTask -TaskName 'SignalRGB Local Bridges' -Confirm:$false
}
Remove-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'SignalRGBLocalBridges' -ErrorAction SilentlyContinue
$launcher=Join-Path $runtime 'logon.vbs'
if (Test-Path -LiteralPath $launcher) { Remove-Item -LiteralPath $launcher }
if (Test-Path -LiteralPath $record) { Remove-Item -LiteralPath $record }
Write-Output 'Demarrage automatique retire pour cet utilisateur.'
if (-not $KeepRunning) { & (Join-Path $PSScriptRoot 'Stop-Bridges.ps1') -ConfigFile $ConfigFile }
