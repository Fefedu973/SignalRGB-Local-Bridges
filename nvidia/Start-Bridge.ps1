param([string]$Python = '',[ValidateRange(0,86400)][int]$Seconds=0,[string]$RuntimeDirectory)
function Resolve-BridgeRuntimeDirectory([string]$Directory) {
    if (-not $Directory) { $Directory = Join-Path $env:LOCALAPPDATA 'NvidiaFeBridge' }
    $Directory = [Environment]::ExpandEnvironmentVariables($Directory)
    if ($Directory -notmatch '^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$))' -or $Directory.IndexOfAny([char[]]@('"', "`r", "`n")) -ge 0) {
        throw 'RuntimeDirectory doit etre un chemin Windows absolu sans guillemets ni retour a la ligne.'
    }
    $absolute = [IO.Path]::GetFullPath($Directory)
    if ($absolute.Length -gt [IO.Path]::GetPathRoot($absolute).Length) { $absolute = $absolute.TrimEnd('\', '/') }
    return $absolute
}
$ErrorActionPreference='Stop'
$stateDir=Resolve-BridgeRuntimeDirectory $RuntimeDirectory
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$runFile=Join-Path $stateDir 'run.json'
if(Test-Path -LiteralPath $runFile){
 $previous=Get-Content -LiteralPath $runFile -Raw | ConvertFrom-Json
 $running=Get-Process -Id $previous.pid -ErrorAction SilentlyContinue
 if($running -and $running.StartTime.ToUniversalTime().Ticks -eq ([datetime]$previous.startedUtc).ToUniversalTime().Ticks){Write-Output 'Le pont NVIDIA est deja actif.';exit 0}
}
if(Get-NetUDPEndpoint -LocalPort 47687 -ErrorAction SilentlyContinue){throw 'UDP47687 est deja utilise. Aucun second pont lance.'}
if(!$Python){
 $localVenv=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
 if(Test-Path -LiteralPath $localVenv){$Python=$localVenv}else{
  $pythonLauncher=Get-Command py.exe -ErrorAction SilentlyContinue
  if($pythonLauncher){
   $Python=(& $pythonLauncher.Source -3 -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
   if($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $Python)){throw 'Python installe introuvable. Fournir -Python.'}
  }else{$Python=(Get-Command python.exe -ErrorAction Stop).Source}
 }
}
$entry=Join-Path $PSScriptRoot 'gpu_bridge.py'
& $Python -B $entry
if($LASTEXITCODE -ne 0){throw 'Le controle NVAPI en lecture seule a echoue.'}
$stop=Join-Path $stateDir ('stop-'+[guid]::NewGuid().ToString('N')+'.signal')
$stdout=Join-Path $stateDir 'stdout.log';$stderr=Join-Path $stateDir 'stderr.log'
$arguments=@('-B',('"'+$entry+'"'),'--serve','--allow-write','--stop-file',('"'+$stop+'"'),'--seconds',$Seconds)
$process=Start-Process -FilePath $Python -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
@{pid=$process.Id;startedUtc=$process.StartTime.ToUniversalTime().ToString('o');stopFile=$stop;stdout=$stdout;stderr=$stderr} | ConvertTo-Json | Set-Content -LiteralPath $runFile -Encoding utf8
Start-Sleep -Milliseconds 500
if($process.HasExited){throw ('Le pont a echoue. Voir '+$stderr)}
Write-Output ('Pont NVIDIA actif, PID '+$process.Id+'. Arreter avec Arreter-pont.cmd.')
