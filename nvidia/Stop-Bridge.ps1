param([string]$RuntimeDirectory)
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
$runFile=Join-Path $stateDir 'run.json'
if(!(Test-Path -LiteralPath $runFile)){Write-Output 'Aucun pont NVIDIA enregistre.';exit 0}
$run=Get-Content -LiteralPath $runFile -Raw | ConvertFrom-Json
$process=Get-Process -Id $run.pid -ErrorAction SilentlyContinue
if(!$process -or $process.StartTime.ToUniversalTime().Ticks -ne ([datetime]$run.startedUtc).ToUniversalTime().Ticks){Write-Output 'Le pont NVIDIA est deja arrete.';exit 0}
$stop=[IO.Path]::GetFullPath($run.stopFile)
if([IO.Path]::GetDirectoryName($stop) -ne [IO.Path]::GetFullPath($stateDir) -or [IO.Path]::GetFileName($stop) -notmatch '^stop-[a-f0-9]{32}\.signal$'){throw 'Chemin de marqueur inattendu.'}
New-Item -ItemType File -Path $stop -Force | Out-Null
if(!$process.WaitForExit(5000)){throw 'Arret encore en cours. Aucun arret force effectue.'}
$last=Get-Content -LiteralPath $run.stdout -Tail 1 | ConvertFrom-Json
if(!$last.shutdown -or $last.shutdown.error -or $last.shutdown.restored_exact -eq $false){throw 'Arret termine sans confirmation de restauration. Consulter les journaux du pont.'}
Write-Output 'Pont NVIDIA arrete proprement; restauration confirmee (ou aucune ecriture).'
