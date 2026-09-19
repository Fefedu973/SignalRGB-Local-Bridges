param([string]$ConfigFile=(Join-Path (Split-Path $PSScriptRoot -Parent) 'local-installation\config.json'),[switch]$Check)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Supervisor.Core.ps1')
$config=Read-StartupConfig $ConfigFile
Test-StartupFiles $config
$taskName='SignalRGB Local Bridges'
$runName='SignalRGBLocalBridges'
$entry=Join-Path $PSScriptRoot 'Start-Supervisor.ps1'
$exe=Get-WindowsPowerShell
if ($ConfigFile.Contains('"')) { throw 'Chemin de configuration invalide.' }
$arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+$entry+'" -ConfigFile "'+$ConfigFile+'"'
$runtime=Get-StartupDirectory
$fallback=New-LogonLauncherPlan $exe $arguments (Join-Path $runtime 'logon.vbs')
if ($Check) {
    Write-Output ('Configuration valide. Entree Run de repli : '+$fallback.RunCommand.Length+' caracteres (maximum260). Aucune modification.')
    exit 0
}
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$method='ScheduledTask'
try {
    $existing=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing -and -not (@($existing.Actions | Where-Object {$_.Arguments -like '*Start-Supervisor.ps1*'}).Count)) {
        throw 'Une tache homonyme appartient a un autre programme.'
    }
    $user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action=New-ScheduledTaskAction -Execute $exe -Argument $arguments
    $trigger=New-ScheduledTaskTrigger -AtLogOn -User $user
    $principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    # Restart is handled inside the supervisor. A Task Scheduler restart queued
    # before a manual stop could otherwise revive bridges after clean shutdown.
    $settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([timespan]::Zero) `
        -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
        -Description 'Ponts SignalRGB locaux : Govee BLE, NVIDIA NVAPI et fond Stream Deck. Aucun droit administrateur.' -Force | Out-Null
    Remove-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name $runName -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $fallback.Path -ErrorAction SilentlyContinue
} catch {
    # Some Windows policies deny even a limited interactive task. HKCU Run has
    # the same per-user/logon lifetime and requires no elevation or credentials.
    $method='HKCU Run'
    if (-not (Test-Path -LiteralPath $fallback.HostPath -PathType Leaf)) { throw 'Windows Script Host absent : le repli HKCU Run ne peut pas etre installe.' }
    foreach ($key in @('HKCU:\Software\Microsoft\Windows Script Host\Settings','HKLM:\Software\Microsoft\Windows Script Host\Settings')) {
        $policy=Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
        if ($policy -and $policy.PSObject.Properties['Enabled'] -and $policy.Enabled -eq 0) {
            throw 'Windows Script Host est desactive par une politique. Aucun contournement effectue.'
        }
    }
    # Keep the Run value short; all long paths live in this user-private launcher.
    $fallback.Content | Set-Content -LiteralPath $fallback.Path -Encoding Unicode
    $runPath='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    New-Item -Path $runPath -Force | Out-Null
    New-ItemProperty -LiteralPath $runPath -Name $runName -Value $fallback.RunCommand -PropertyType String -Force | Out-Null
}
@{method=$method;task=$taskName;runName=$runName;installedUtc=[datetime]::UtcNow.ToString('o');entry=$entry;config=$ConfigFile} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime 'autostart.json') -Encoding UTF8
Write-Output ('Demarrage automatique installe : '+$method+'. Il prendra effet a la prochaine ouverture de session.')
Write-Output 'Pour cette session : Demarrer-tout.cmd. Aucun processus lance par cet installeur.'
