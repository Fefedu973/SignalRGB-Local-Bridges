param([string]$ConfigFile=(Join-Path (Split-Path $PSScriptRoot -Parent) 'local-installation\config.json'))
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Supervisor.Core.ps1')
$config=Read-StartupConfig $ConfigFile
Test-StartupFiles $config
$runtime=Get-StartupDirectory
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
if ($ConfigFile.Contains('"')) { throw 'Chemin de configuration invalide.' }
$entry=Join-Path $PSScriptRoot 'Start-Supervisor.ps1'
Start-Process -FilePath (Get-WindowsPowerShell) -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
    '-File',('"'+$entry+'"'),'-ConfigFile',('"'+$ConfigFile+'"')) -WindowStyle Hidden | Out-Null
Write-Output 'Superviseur demande. Un second lancement est ignore si le premier est deja actif.'
Write-Output ('Journal : '+(Join-Path $runtime 'supervisor.jsonl'))
