param(
    [Parameter(Mandatory=$true)][Alias('PythonPath')][string]$Python,
    [Alias('HubRoot')][string]$HubDirectory = (Split-Path $PSScriptRoot -Parent),
    [Alias('GoveeRoot')][string]$GoveeDirectory,
    [string]$GoveePython,
    [string]$SignalRGBPluginDirectory='',
    [string]$ConfigFile=(Join-Path (Split-Path $PSScriptRoot -Parent) 'local-installation\config.json'),
    [switch]$Force
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Supervisor.Core.ps1')
if ((Test-Path -LiteralPath $ConfigFile) -and -not $Force) { throw 'Configuration deja presente. Utilisez -Force pour la remplacer explicitement.' }
if (-not $GoveeDirectory) { $GoveeDirectory=Join-Path (Split-Path $HubDirectory -Parent) 'signalrgb-govee-direct-connect\ble-companion' }
if (-not $GoveePython) { $GoveePython=Join-Path (Split-Path $GoveeDirectory -Parent) '.venv\Scripts\python.exe' }
$streamDirectory=Join-Path $HubDirectory 'streamdeck\bridge'
$privateDirectory=Join-Path $HubDirectory 'local-installation'
$config=[ordered]@{
    schema_version=1; python=$Python
    govee=[ordered]@{directory=$GoveeDirectory;python=$GoveePython;config_file=(Join-Path $privateDirectory 'govee\config.local.json')}
    nvidia=@{directory=(Join-Path $HubDirectory 'nvidia');runtime_directory=(Join-Path $privateDirectory 'nvidia')}
    streamdeck=[ordered]@{directory=$streamDirectory;venv_directory=(Join-Path $streamDirectory '.venv');
        plugin_directory=$SignalRGBPluginDirectory;elgato_directory=(Join-Path $env:ProgramFiles 'Elgato\StreamDeck');
        runtime_directory=(Join-Path $privateDirectory 'streamdeck')}
}
# No OEM key or session token belongs in this path-only configuration.
New-Item -ItemType Directory -Path (Split-Path $ConfigFile -Parent) -Force | Out-Null
$temporary=$ConfigFile+'.new'
try {
    $config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporary -Encoding UTF8
    $parsed=Read-StartupConfig $temporary
    Test-StartupFiles $parsed
    Move-Item -LiteralPath $temporary -Destination $ConfigFile -Force
} finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary } }
Write-Output ('Configuration privee creee : '+$ConfigFile)
Write-Output 'Aucun pont lance et aucun demarrage automatique enregistre.'
