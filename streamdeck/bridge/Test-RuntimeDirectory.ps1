$ErrorActionPreference = 'Stop'
$hub = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$passed = 0
foreach ($relative in @('streamdeck\bridge\Start-Bridge.ps1','streamdeck\bridge\Stop-Bridge.ps1','nvidia\Start-Bridge.ps1','nvidia\Stop-Bridge.ps1')) {
    $tokens = $null; $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $hub $relative), [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ('Syntax error: ' + $relative) }
    $node = $ast.Find({param($item) $item -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $item.Name -eq 'Resolve-BridgeRuntimeDirectory'}, $false)
    if (-not $node) { throw ('Runtime resolver missing: ' + $relative) }
    # Execute only this pure path resolver, never the launcher body.
    . ([scriptblock]::Create($node.Extent.Text))
    if ((Resolve-BridgeRuntimeDirectory 'C:\private runtime\nested\..\') -ne 'C:\private runtime') { throw 'Canonicalization failed' }
    $passed++
    if ((Resolve-BridgeRuntimeDirectory 'C:\') -ne 'C:\') { throw 'Drive root was corrupted' }
    $passed++
    if ((Resolve-BridgeRuntimeDirectory '\\server\share\folder\') -ne '\\server\share\folder') { throw 'UNC normalization failed' }
    $passed++
    $suffix = if ($relative.StartsWith('streamdeck')) { 'CodexLocalBridges\StreamDeck\runtime' } else { 'NvidiaFeBridge' }
    if ((Resolve-BridgeRuntimeDirectory '') -ne [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA $suffix))) { throw 'Legacy default changed' }
    $passed++
    foreach ($invalid in @('relative', 'C:relative', '\drive-relative', '\\server', 'C:\bad"quote', "C:\bad`nline")) {
        $threw = $false
        try { [void](Resolve-BridgeRuntimeDirectory $invalid) } catch { $threw = $true }
        if (-not $threw) { throw ('Unsafe runtime accepted: ' + $relative) }
        $passed++
    }
}
Write-Output ($passed.ToString() + ' runtime path checks passed; no launcher or bridge was executed.')
