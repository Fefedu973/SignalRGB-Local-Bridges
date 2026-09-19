$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Supervisor.Core.ps1')
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('signalrgb-launcher-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
$passed=0
try {
    'param([int]$Code); Write-Output "fixture complete"; exit $Code' |
        Set-Content -LiteralPath (Join-Path $temporary 'Start-Bridge.ps1') -Encoding UTF8
    'Write-Output "cleanup fixture complete"; exit 0' |
        Set-Content -LiteralPath (Join-Path $temporary 'Stop-Bridge.ps1') -Encoding UTF8
    foreach ($expected in @(0,3)) {
        $bridge=[pscustomobject]@{Name='fixture';Directory=$temporary;StartArgs=@('-Code',$expected);StopArgs=@()}
        $process=Start-BridgeLauncher $bridge 'Start' $temporary $null
        try {
            if (-not $process.WaitForExit(5000)) { throw 'La fixture ne se termine pas.' }
            $actual=Get-LauncherExitCode $process
            if ($null -eq $actual -or $actual -ne $expected) { throw ('Code attendu '+$expected+', obtenu ['+$actual+'].') }
            $passed++
            if (-not ([IO.File]::ReadAllText((Join-Path $temporary 'fixture-start.stdout.log')).Contains('fixture complete'))) { throw 'Sortie redirigee incomplete.' }
            $passed++
        } finally { $process.Dispose() }
    }
    $process=Start-BridgeLauncher $bridge 'Stop' $temporary $null
    try {
        if (-not $process.WaitForExit(5000) -or (Get-LauncherExitCode $process) -ne 0) { throw 'Code de nettoyage incorrect.' }
        $passed++
    } finally { $process.Dispose() }
} finally {
    $resolved=[IO.Path]::GetFullPath($temporary)
    $parent=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')+'\'
    if (-not $resolved.StartsWith($parent,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notlike 'signalrgb-launcher-test-*') { throw 'Nettoyage de test hors limites refuse.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Output ($passed.ToString()+' assertions de codes de sortie reussies. Fixtures uniquement, aucun pont lance.')
