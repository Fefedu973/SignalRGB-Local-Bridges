$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Supervisor.Core.ps1')
$passed = 0
function Assert-HashTest($Actual, $Expected, [string]$Label) {
    if ($Actual -cne $Expected) { throw ($Label + ': unexpected result') }
    $script:passed++
}

# Prove that the production build guard does not invoke the unavailable cmdlet.
function Get-FileHash { throw 'Get-FileHash is deliberately unavailable in this test.' }
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('signalrgb-hash-test-' + [guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($temporary) | Out-Null
try {
    $file = Join-Path $temporary 'known data.bin'
    [IO.File]::WriteAllBytes($file, [byte[]]@())
    Assert-HashTest (Get-StartupSha256 $file) 'E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855' 'Empty SHA256 vector'
    [IO.File]::WriteAllBytes($file, [byte[]]@(97,98,99))
    $abc = 'BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD'
    Assert-HashTest (Get-StartupSha256 $file) $abc 'abc SHA256 vector'
    $exclusive = [IO.File]::Open($file, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $exclusive.Dispose()
    Assert-HashTest ([IO.File]::Exists($file)) $true 'Hash releases its file handle'

    $lines = @('HASHES = {')
    foreach ($name in @('StreamDeck.exe','Qt6Gui.dll','Qt6Core.dll')) {
        [IO.File]::WriteAllBytes((Join-Path $temporary $name), [byte[]]@(97,98,99))
        $lines += ('    "' + $name + '": "' + $abc + '",')
    }
    $lines += '}'
    [IO.File]::WriteAllText((Join-Path $temporary 'background_api.py'), ($lines -join "`n"))
    $config = [pscustomobject]@{streamdeck=[pscustomobject]@{directory=$temporary;elgato_directory=$temporary}}
    Assert-HashTest (Get-StreamBuild $config).Supported $true 'Build guard works without Get-FileHash'
    [IO.File]::WriteAllBytes((Join-Path $temporary 'Qt6Gui.dll'), [byte[]]@(0,1,2,3))
    Assert-HashTest (Get-StreamBuild $config).Supported $false 'Changed DLL is refused'
    [IO.File]::Delete((Join-Path $temporary 'Qt6Core.dll'))
    Assert-HashTest (Get-StreamBuild $config).Supported $false 'Missing DLL is refused'
    $threw = $false
    try { [void](Get-StartupSha256 (Join-Path $temporary 'missing.bin')) } catch { $threw = $true }
    Assert-HashTest $threw $true 'Missing file never yields a trusted hash'
} finally {
    $resolved = [IO.Path]::GetFullPath($temporary)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notlike 'signalrgb-hash-test-*') {
        throw 'Refusing cleanup outside the fresh test directory.'
    }
    [IO.Directory]::Delete($resolved, $true)
}
Write-Output ($passed.ToString() + ' SHA256 checks passed; no bridge, app, registry, or task was changed.')
