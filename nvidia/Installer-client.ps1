param([string]$PluginDirectory='')
$ErrorActionPreference='Stop'
if(!$PluginDirectory){$PluginDirectory=Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WhirlwindFX\Plugins'}
if(!(Test-Path -LiteralPath $PluginDirectory -PathType Container)){throw 'Dossier Plugins SignalRGB introuvable. Fournir -PluginDirectory.'}
foreach($name in @('NVIDIA_RTX3080Ti_FE_Bridge.qml','NVIDIA_RTX3080Ti_FE_Bridge.js')){
 $target=Join-Path $PluginDirectory $name
 if(Test-Path -LiteralPath $target){
  $backupDir=Join-Path $env:LOCALAPPDATA 'NvidiaFeBridge\backups';New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
  Copy-Item -LiteralPath $target -Destination (Join-Path $backupDir ((Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+$name))
 }
 Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $target
 Write-Output ('Client installe : '+$target)
}
