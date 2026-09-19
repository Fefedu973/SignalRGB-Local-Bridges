$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Supervisor.Core.ps1')
$script:passed=0
function Assert-Equal($Actual,$Expected,[string]$Label) {
    if ($Actual -cne $Expected) { throw ($Label+': attendu '+$Expected+', obtenu '+$Actual) }
    $script:passed++
}
function Observe([string]$Name='govee',[bool]$Port=$false,[bool]$Runner=$false,[bool]$Launcher=$false,[int]$Elgato=1,[bool]$Supported=$true) {
    [pscustomobject]@{Name=$Name;PortOpen=$Port;RunnerAlive=$Runner;LauncherAlive=$Launcher;ElgatoCount=$Elgato;BuildSupported=$Supported}
}
foreach ($path in (Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1')) {
    $tokens=$null; $errors=$null
    [void][System.Management.Automation.Language.Parser]::ParseFile($path.FullName,[ref]$tokens,[ref]$errors)
    Assert-Equal $errors.Count 0 ('Syntaxe '+$path.Name)
}
$now=[datetime]::UtcNow
$past=$now.AddMinutes(-1)
Assert-Equal (Get-BridgeDecision (Observe -Port $true) $now $past) 'running' 'Port legacy occupe : pas de doublon'
Assert-Equal (Get-BridgeDecision (Observe -Runner $true) $now $past) 'waiting-process' 'Pont vivant sans port : pas de doublon'
Assert-Equal (Get-BridgeDecision (Observe -Launcher $true) $now $past) 'waiting-process' 'Lanceur encore actif : pas de chevauchement'
Assert-Equal (Get-BridgeDecision (Observe -Name 'streamdeck' -Elgato 0) $now $past) 'waiting-elgato' 'Elgato absent'
Assert-Equal (Get-BridgeDecision (Observe -Name 'streamdeck' -Elgato 2) $now $past) 'waiting-elgato' 'Deux processus Elgato : pas d attachement arbitraire'
Assert-Equal (Get-BridgeDecision (Observe -Name 'streamdeck' -Supported $false) $now $past) 'unsupported-elgato' 'Build inconnu : aucun attachement'
Assert-Equal (Get-BridgeDecision (Observe) $now $now.AddSeconds(1)) 'backoff' 'Temporisation apres echec'
Assert-Equal (Get-BridgeDecision (Observe) $now $past) 'start' 'Redemarrage apres disparition complete'
Assert-Equal (Get-RetryDelay 1) 5 'Premier retry'
Assert-Equal (Get-RetryDelay 2) 15 'Deuxieme retry'
Assert-Equal (Get-RetryDelay 3) 60 'Troisieme retry'
Assert-Equal (Get-RetryDelay 99) 300 'Reprises ulterieures bornees'
$example=Read-StartupConfig (Join-Path $PSScriptRoot 'config.example.json')
Assert-Equal $example.schema_version 1 'Schema'
Assert-Equal ([IO.Path]::IsPathRooted($example.python)) $true 'Expansion des chemins'
Assert-Equal ((Get-BridgeDefinitions $example).Count) 3 'Trois ponts independants'
Assert-Equal ((Get-StartupDirectory).Contains('local-installation\startup')) $true 'Runtime partage hors AppData virtualise'
$definitions=Get-BridgeDefinitions $example
foreach ($name in @('nvidia','streamdeck')) {
    $definition=$definitions | Where-Object Name -eq $name
    Assert-Equal $definition.RunFile.StartsWith($example.$name.runtime_directory) $true ('RunFile partage '+$name)
    Assert-Equal ($definition.StartArgs -contains '-RuntimeDirectory') $true ('Runtime explicite au demarrage '+$name)
    Assert-Equal ($definition.StopArgs -contains '-RuntimeDirectory') $true ('Meme runtime a l arret '+$name)
}
Assert-Equal ([IO.Path]::IsPathRooted((Get-LimitedProcessImage $PID))) $true 'Image du processus en lecture limitee'
$plan=New-LogonLauncherPlan (Get-WindowsPowerShell) '-File "C:\folder with spaces\entry.ps1" -ConfigFile "C:\private folder\config.json"' (Join-Path (Get-StartupDirectory) 'logon.vbs')
Assert-Equal ($plan.RunCommand.Length -le 260) $true 'HKCU Run ne depasse pas260 caracteres'
Assert-Equal ($plan.Content.Contains('""C:\private folder\config.json""')) $true 'Guillemets des chemins preserves en VBScript'
$longRejected=$false
try { [void](New-LogonLauncherPlan (Get-WindowsPowerShell) '' ('C:\'+('x'*260)+'\logon.vbs')) } catch { $longRejected=$true }
Assert-Equal $longRejected $true 'Entree Run trop longue refusee avant toute ecriture'

$temporary=Join-Path ([IO.Path]::GetTempPath()) ('signalrgb-startup-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $lines=@('HASHES = {')
    foreach ($name in @('StreamDeck.exe','Qt6Gui.dll','Qt6Core.dll')) {
        [IO.File]::WriteAllText((Join-Path $temporary $name),('fixture '+$name))
        $hash=(Get-FileHash -LiteralPath (Join-Path $temporary $name)).Hash
        $lines += ('    "'+$name+'": "'+$hash+'",')
    }
    $lines+='}'
    $lines | Set-Content -LiteralPath (Join-Path $temporary 'background_api.py') -Encoding UTF8
    $fake=[pscustomobject]@{streamdeck=[pscustomobject]@{directory=$temporary;elgato_directory=$temporary}}
    Assert-Equal (Get-StreamBuild $fake).Supported $true 'Les trois empreintes sont exactes'
    [IO.File]::WriteAllText((Join-Path $temporary 'Qt6Core.dll'),'updated fixture')
    Assert-Equal (Get-StreamBuild $fake).Supported $false 'Mise a jour Qt bloque le pont'
    [IO.File]::WriteAllText((Join-Path $temporary 'StreamDeck.exe'),'updated fixture')
    Assert-Equal (Get-StreamBuild $fake).Supported $false 'Mise a jour Elgato reste bloquee'
    # Execute only a harmless file fixture to verify real WScript quoting/hiding.
    $fixture=Join-Path $temporary 'hidden fixture.ps1'
    '[IO.File]::WriteAllText((Join-Path $PSScriptRoot "hidden proof.txt"),"ok")' | Set-Content -LiteralPath $fixture -Encoding UTF8
    $hiddenPlan=New-LogonLauncherPlan (Get-WindowsPowerShell) ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$fixture+'"') (Join-Path $temporary 'logon fixture.vbs')
    $hiddenPlan.Content | Set-Content -LiteralPath $hiddenPlan.Path -Encoding Unicode
    $testHost=Start-Process -FilePath $hiddenPlan.HostPath -ArgumentList @('//B','//Nologo',('"'+$hiddenPlan.Path+'"')) -WindowStyle Hidden -PassThru
    [void]$testHost.WaitForExit(5000)
    $proof=Join-Path $temporary 'hidden proof.txt'
    $limit=[datetime]::UtcNow.AddSeconds(5)
    while (-not (Test-Path -LiteralPath $proof) -and [datetime]::UtcNow -lt $limit) { Start-Sleep -Milliseconds 100 }
    Assert-Equal (Test-Path -LiteralPath $proof) $true 'WScript lance la fixture avec espaces sans fenetre'
    Assert-Equal ([IO.File]::ReadAllText($proof)) 'ok' 'Le chemin cite atteint la bonne fixture'
    # Verify the singleton against a separate process, without launching a bridge.
    $mutexName='Local\SignalRGBStartupTest-'+[guid]::NewGuid().ToString('N')
    $guard=New-Object Threading.Mutex($true,$mutexName)
    try {
        $child=Join-Path $temporary 'mutex-test.ps1'
        @('
param([string]$Name)
$guard=New-Object Threading.Mutex($false,$Name)
try { if ($guard.WaitOne(0)) { $guard.ReleaseMutex(); exit 9 }; exit 0 } finally { $guard.Dispose() }
') | Set-Content -LiteralPath $child -Encoding UTF8
        & (Get-WindowsPowerShell) -NoProfile -NonInteractive -File $child -Name $mutexName
        Assert-Equal $LASTEXITCODE 0 'Un second processus ne peut pas prendre le verrou'
    } finally { $guard.ReleaseMutex(); $guard.Dispose() }
} finally {
    # Only the freshly created, verified test directory is removed recursively.
    $resolved=[IO.Path]::GetFullPath($temporary)
    $parent=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')+'\'
    if (-not $resolved.StartsWith($parent,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notlike 'signalrgb-startup-test-*') { throw 'Refus de nettoyage hors du dossier de test.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Output ($script:passed.ToString()+' assertions hors materiel reussies. Aucun pont, appareil, registre ni tache planifiee modifies.')
