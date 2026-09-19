param([string]$ConfigFile=(Join-Path (Split-Path $PSScriptRoot -Parent) 'local-installation\config.json'))
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Supervisor.Core.ps1')
$config=Read-StartupConfig $ConfigFile
$runtime=Get-StartupDirectory
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $runtime 'supervisor.stop'),'stop')
$stateFile=Join-Path $runtime 'supervisor.json'
$running=$null
if (Test-Path -LiteralPath $stateFile) {
    $state=Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $candidate=Get-Process -Id $state.pid -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.StartTime.ToUniversalTime().Ticks -eq ([datetime]$state.startedUtc).ToUniversalTime().Ticks) { $running=$candidate }
}
if ($running) {
    if (-not $running.WaitForExit(90000)) { throw 'Nettoyage encore en cours. Aucun processus tue. Consultez les journaux avant de relancer.' }
    $pending=@(Get-BridgeDefinitions $config | Where-Object {Get-BridgeRunner $_})
    if ($pending.Count) { throw 'Un pont termine encore son nettoyage. Aucun arret force effectue.' }
    $last=Get-Content -LiteralPath (Join-Path $runtime 'supervisor.jsonl') -Tail 1 | ConvertFrom-Json
    if ($last.event -ne 'stopped' -or $last.detail -ne 'clean=True') {
        throw 'Les processus sont termines, mais le nettoyage complet n est pas confirme. Consultez les journaux.'
    }
} else {
    if (-not (Stop-ConfiguredBridges $config $runtime)) { throw 'Un pont ne confirme pas encore son arret propre. Consultez les journaux.' }
}
Write-Output 'Superviseur et ponts arretes proprement. Les applications SignalRGB et Elgato restent ouvertes.'
Write-Output 'Le demarrage automatique reste installe. Utilisez Desactiver-demarrage.cmd pour le retirer.'
