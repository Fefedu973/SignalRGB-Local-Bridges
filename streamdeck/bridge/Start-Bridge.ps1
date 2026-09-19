param(
    [string]$SignalRGBPluginDirectory,
    [string]$Python,
    [string]$VenvDirectory,
    [string]$RuntimeDirectory
)
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
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    $session = Join-Path $runtime 'api-session.json'
    $stop = Join-Path $runtime 'bridge.stop'
    $output = Join-Path $runtime 'background-api.jsonl'
    $state = Join-Path $runtime 'launcher.json'
    # Refuse before any attachment if another API already owns our port.
    $probe = New-Object System.Net.Sockets.TcpClient
    try { $probe.Connect('127.0.0.1', 47686); $occupied = $true }
    catch { $occupied = $false }
    finally { $probe.Dispose() }
    if ($occupied) { throw 'Un pont utilise deja le port 47686. Arretez-le proprement avant de redemarrer.' }
    if (Test-Path -LiteralPath $state) {
        $old = Get-Content -LiteralPath $state -Raw | ConvertFrom-Json
        if (Get-Process -Id $old.runner_pid -ErrorAction SilentlyContinue) {
            throw 'Le lanceur precedent est encore actif. Utilisez Arreter-StreamDeck.cmd.'
        }
    }
    $targets = @(Get-Process -Name StreamDeck -ErrorAction SilentlyContinue)
    if ($targets.Count -ne 1) { throw 'Ouvrez Stream Deck : exactement un processus StreamDeck doit fonctionner.' }
    if (-not $VenvDirectory) { $VenvDirectory = Join-Path $PSScriptRoot '.venv' }
    $VenvDirectory = [System.IO.Path]::GetFullPath($VenvDirectory)
    $bridgePython = Join-Path $VenvDirectory 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $bridgePython)) {
        if (-not $Python) { $Python = 'python.exe' }
        $basePython = Get-Command -Name $Python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $basePython) { throw 'Installez Python 3.10+ x64 et rendez python.exe disponible dans PATH.' }
        & $basePython.Source -c 'import sys, struct; assert sys.version_info >= (3,10) and struct.calcsize(chr(80)) == 8'
        if ($LASTEXITCODE -ne 0) { throw 'Le Python de creation doit etre Python 3.10+ x64.' }
        & $basePython.Source -m venv $VenvDirectory
        if ($LASTEXITCODE -ne 0) { throw 'Creation de l environnement Python impossible.' }
        & $bridgePython -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Installation de Frida impossible. Consultez le message precedent.' }
    }
    & $bridgePython -c 'import sys, struct; assert sys.version_info >= (3,10) and struct.calcsize(chr(80)) == 8'
    if ($LASTEXITCODE -ne 0) { throw 'L environnement choisi doit utiliser Python 3.10+ x64.' }
    & $bridgePython -c 'import frida, PIL; assert tuple(map(int, frida.__version__.split(chr(46)))) == (17,18,0) and tuple(map(int, PIL.__version__.split(chr(46)))) == (12,3,0)'
    if ($LASTEXITCODE -ne 0) {
        & $bridgePython -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Installation des dependances du pont impossible.' }
    }
    if (-not $SignalRGBPluginDirectory) {
        $known = Join-Path $env:USERPROFILE 'OneDrive\Documents\WhirlwindFX\Plugins'
        if (Test-Path -LiteralPath $known -PathType Container) { $SignalRGBPluginDirectory = $known }
    }
    if (Test-Path -LiteralPath $stop) { Remove-Item -LiteralPath $stop }
    if (Test-Path -LiteralPath $session) { Remove-Item -LiteralPath $session }
    $arguments = @(
        ('"{0}"' -f (Join-Path $PSScriptRoot 'background_api.py')),
        '--pid', $targets[0].Id, '--seconds', '0', '--install-signalrgb',
        '--session-file', ('"{0}"' -f $session), '--stop-file', ('"{0}"' -f $stop),
        '--output', ('"{0}"' -f $output)
    )
    if ($RuntimeDirectory) { $arguments += @('--runtime-directory', ('"{0}"' -f $runtime)) }
    if ($SignalRGBPluginDirectory) {
        $arguments += @('--signalrgb-plugin-dir', ('"{0}"' -f $SignalRGBPluginDirectory))
    }
    $runner = Start-Process -FilePath $bridgePython -ArgumentList $arguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runtime 'launcher-stdout.log') `
        -RedirectStandardError (Join-Path $runtime 'launcher-stderr.log')
    @{ runner_pid = $runner.Id; streamdeck_pid = $targets[0].Id; stop_file = $stop; output = $output } |
        ConvertTo-Json | Set-Content -LiteralPath $state -Encoding UTF8
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 250
        $activeRunner = Get-Process -Id $runner.Id -ErrorAction SilentlyContinue
        if (-not $activeRunner) { throw "Le pont a refuse le demarrage. Consultez $output et launcher-stderr.log dans $runtime" }
        $published = (Test-Path -LiteralPath $output) -and
            ((Get-Content -LiteralPath $output -Raw) -match '"event":\s*"signalrgb-client-installed"')
        if ((Test-Path -LiteralPath $session) -and $published) {
            Write-Host 'Pont demarre. SignalRGB pilote le fond ; les icones restent gerees par Stream Deck.'
            Write-Host 'Le premier rendu naturel peut prendre une minute. Utilisez Arreter-StreamDeck.cmd pour terminer.'
            exit 0
        }
    }
    throw "Demarrage en attente. Consultez $output. Pour annuler proprement, utilisez Arreter-StreamDeck.cmd."
} catch { Write-Error $_; exit 1 }
