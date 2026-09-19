param([string]$ConfigFile = (Join-Path (Split-Path $PSScriptRoot -Parent) 'local-installation\config.json'), [switch]$Check)
$ErrorActionPreference = 'Stop'
# This trap also covers failures before Core/config/mutex initialization. Use
# only .NET here so a broken module search path cannot hide the startup error.
trap {
    try {
        $bootstrapDirectory=[IO.Path]::Combine([IO.Directory]::GetParent($PSScriptRoot).FullName,'local-installation','startup')
        [void][IO.Directory]::CreateDirectory($bootstrapDirectory)
        $message=[datetime]::UtcNow.ToString('o')+' BOOTSTRAP ERROR '+$_.Exception.ToString()+"`r`n"+$_.InvocationInfo.PositionMessage+"`r`n"
        [IO.File]::AppendAllText([IO.Path]::Combine($bootstrapDirectory,'bootstrap.log'),$message)
    } catch { }
    exit 1
}
. (Join-Path $PSScriptRoot 'Supervisor.Core.ps1')
$config = Read-StartupConfig $ConfigFile
Test-StartupFiles $config
if ($Check) {
    $build = Get-StreamBuild $config
    [pscustomobject]@{Configuration='OK'; StreamDeckBuildSupported=$build.Supported; HardwareActions='none'} | ConvertTo-Json
    exit 0
}
$runtime = Get-StartupDirectory
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$mutex = New-Object Threading.Mutex($false, ('Local\SignalRGBLocalBridges-'+$identity))
$ownsMutex = $false
try { $ownsMutex = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $ownsMutex=$true }
if (-not $ownsMutex) { $mutex.Dispose(); exit 0 }
$stopFile = Join-Path $runtime 'supervisor.stop'
$runFile = Join-Path $runtime 'supervisor.json'
$logFile = Join-Path $runtime 'supervisor.jsonl'
function Write-SupervisorLog([string]$Event, [string]$Bridge='', [string]$Detail='') {
    if ((Test-Path -LiteralPath $logFile) -and (Get-Item -LiteralPath $logFile).Length -gt 2097152) {
        Move-Item -LiteralPath $logFile -Destination ($logFile+'.previous') -Force
    }
    @{time=[datetime]::UtcNow.ToString('o');event=$Event;bridge=$Bridge;detail=$Detail} | ConvertTo-Json -Compress |
        Add-Content -LiteralPath $logFile -Encoding UTF8
}
$states = @{}
$streamStamp = ''
$streamBuild = $null
try {
    Remove-Item -LiteralPath $stopFile -ErrorAction SilentlyContinue
    @{pid=$PID;startedUtc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o');config=$ConfigFile} |
        ConvertTo-Json | Set-Content -LiteralPath $runFile -Encoding UTF8
    Write-SupervisorLog 'started'
    foreach ($bridge in (Get-BridgeDefinitions $config)) {
        $states[$bridge.Name] = @{Failures=0;Next=[datetime]::MinValue;Launcher=$null;Decision='';HealthySince=$null;AwaitingReady=$false}
    }
    while (-not (Test-Path -LiteralPath $stopFile)) {
        foreach ($bridge in (Get-BridgeDefinitions $config)) {
            if (Test-Path -LiteralPath $stopFile) { break }
            $state = $states[$bridge.Name]
            $now = [datetime]::UtcNow
            $launchAlive = $false
            if ($state.Launcher) {
                $state.Launcher.Refresh()
                $launchAlive = -not $state.Launcher.HasExited
                if (-not $launchAlive) {
                    $exitCode=Get-LauncherExitCode $state.Launcher
                    if ($null -eq $exitCode) {
                        Write-SupervisorLog 'launcher-exit-unknown' $bridge.Name 'Code indisponible ; verification par processus et port, sans compter un echec du lanceur.'
                    } elseif ($exitCode -ne 0) {
                        $state.AwaitingReady=$false
                        $state.Failures++
                        $state.Next=$now.AddSeconds((Get-RetryDelay $state.Failures))
                        Write-SupervisorLog 'launcher-failed' $bridge.Name ('exit='+$exitCode+'; retry_after='+$state.Next.ToString('o'))
                    }
                    $state.Launcher.Dispose(); $state.Launcher=$null
                }
            }
            $port = Test-BridgePort $bridge
            $runner = Get-BridgeRunner $bridge
            if ($state.AwaitingReady -and -not $port -and -not $runner -and -not $launchAlive) {
                $state.AwaitingReady=$false; $state.Failures++
                $state.Next=$now.AddSeconds((Get-RetryDelay $state.Failures))
                Write-SupervisorLog 'exited-before-ready' $bridge.Name ('retry_after='+$state.Next.ToString('o'))
            }
            $elgatoCount = 0; $buildSupported=$false
            if ($bridge.Name -eq 'streamdeck' -and -not $port -and -not $runner -and -not $launchAlive) {
                $targets = @(Get-Process -Name StreamDeck -ErrorAction SilentlyContinue)
                $elgatoCount = $targets.Count
                if ($elgatoCount -eq 1) {
                    $stamp = Get-StreamFileStamp $config
                    if ($stamp -ne $streamStamp) {
                        $streamBuild = Get-StreamBuild $config
                        $streamStamp=$stamp
                        # A newly installed/revalidated build may recover immediately.
                        $state.Next=[datetime]::MinValue; $state.Failures=0
                    }
                    try { $targetImage = Get-LimitedProcessImage $targets[0].Id } catch { $targetImage=$null }
                    $buildSupported = $streamBuild.Supported -and ($targetImage -eq (Join-Path $config.streamdeck.elgato_directory 'StreamDeck.exe'))
                }
            }
            $observation = [pscustomobject]@{Name=$bridge.Name;PortOpen=$port;RunnerAlive=[bool]$runner;LauncherAlive=$launchAlive;ElgatoCount=$elgatoCount;BuildSupported=$buildSupported}
            $decision = Get-BridgeDecision $observation $now $state.Next
            if ($decision -ne $state.Decision) { Write-SupervisorLog $decision $bridge.Name; $state.Decision=$decision }
            if ($decision -eq 'running') {
                $state.AwaitingReady=$false
                if (-not $state.HealthySince) { $state.HealthySince=$now }
                if (($now-$state.HealthySince).TotalSeconds -ge 60) { $state.Failures=0 }
                continue
            }
            if ($state.HealthySince) {
                $state.HealthySince=$null; $state.Failures++
                $state.Next=$now.AddSeconds((Get-RetryDelay $state.Failures))
                continue
            }
            if ($decision -eq 'start') {
                $state.Launcher = Start-BridgeLauncher $bridge 'Start' $runtime $config
                $state.AwaitingReady=$true
                # Reserve a startup window even when the wrapper exits before readiness.
                $state.Next=$now.AddSeconds(30)
                Write-SupervisorLog 'launch-requested' $bridge.Name
            }
        }
        for ($tick=0; $tick -lt 10 -and -not (Test-Path -LiteralPath $stopFile); $tick++) { Start-Sleep -Seconds 1 }
    }
    # Let in-flight wrappers finish before asking their bridge to release resources.
    foreach ($state in $states.Values) {
        if ($state.Launcher -and -not $state.Launcher.HasExited) {
            Write-SupervisorLog 'waiting-launcher-before-cleanup'
            # Never leave a delayed launcher free to start a new bridge after stop.
            while (-not $state.Launcher.WaitForExit(1000)) { }
        }
    }
    $clean = Stop-ConfiguredBridges $config $runtime
    Write-SupervisorLog 'stopped' '' ('clean='+$clean)
} catch {
    Write-SupervisorLog 'supervisor-error' '' $_.Exception.Message
    throw
} finally {
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
