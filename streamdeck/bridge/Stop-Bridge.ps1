param([string]$RuntimeDirectory)
function Resolve-BridgeRuntimeDirectory([string]$Directory) {
    if (-not $Directory) { $Directory = Join-Path $env:LOCALAPPDATA 'CodexLocalBridges\StreamDeck\runtime' }
    $Directory = [Environment]::ExpandEnvironmentVariables($Directory)
    if ($Directory -notmatch '^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$))' -or $Directory.IndexOfAny([char[]]@('"', "`r", "`n")) -ge 0) {
        throw 'RuntimeDirectory doit etre un chemin Windows absolu sans guillemets ni retour a la ligne.'
    }
    $absolute = [IO.Path]::GetFullPath($Directory)
    if ($absolute.Length -gt [IO.Path]::GetPathRoot($absolute).Length) { $absolute = $absolute.TrimEnd('\', '/') }
    return $absolute
}
$ErrorActionPreference = 'Stop'
try {
    $runtime = Resolve-BridgeRuntimeDirectory $RuntimeDirectory
    $state = Join-Path $runtime 'launcher.json'
    if (-not (Test-Path -LiteralPath $state)) { Write-Host 'Aucune session lancee par ce raccourci.'; exit 0 }
    $metadata = Get-Content -LiteralPath $state -Raw | ConvertFrom-Json
    # Never accept a file path from session metadata: this control owns one path.
    $stop = Join-Path $runtime 'bridge.stop'
    [System.IO.File]::WriteAllText($stop, '')
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (-not (Get-Process -Id $metadata.runner_pid -ErrorAction SilentlyContinue)) {
            $log = Get-Content -LiteralPath (Join-Path $runtime 'background-api.jsonl') -Raw
            if (-not $log.Contains('"event": "api-finished"') -or -not $log.Contains('"event": "script-unloaded"')) {
                throw 'Le processus est termine sans confirmation de nettoyage. Consultez le journal avant de redemarrer.'
            }
            Write-Host 'Pont arrete. Le fond normal a ete demande et les hooks detaches.'
            Write-Host "Journal de verification : $(Join-Path $runtime 'background-api.jsonl')"
            exit 0
        }
        Start-Sleep -Milliseconds 250
    }
    Write-Host 'Arret demande ; le processus termine son nettoyage. Ne le tuez pas.'
    exit 1
} catch { Write-Error $_; exit 1 }
