Set-StrictMode -Version 2

function Get-StartupDirectory {
    Join-Path (Split-Path $PSScriptRoot -Parent) 'local-installation\startup'
}

function Get-WindowsPowerShell {
    # Launchers work identically when invoked from PowerShell 7 or Windows 5.1.
    Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
}

function New-LogonLauncherPlan([string]$Executable, [string]$Arguments, [string]$LauncherPath) {
    $hostPath=Join-Path $env:WINDIR 'System32\wscript.exe'
    foreach ($path in @($Executable,$LauncherPath,$hostPath)) {
        if (-not [IO.Path]::IsPathRooted($path) -or $path.Contains('"') -or $path.Contains("`r") -or $path.Contains("`n")) {
            throw 'Chemin du lanceur de session invalide.'
        }
    }
    if ($Arguments.Contains("`r") -or $Arguments.Contains("`n")) { throw 'Arguments du lanceur de session invalides.' }
    $runCommand='"'+$hostPath+'" //B //Nologo "'+$LauncherPath+'"'
    if ($runCommand.Length -gt 260) { throw 'Entree HKCU Run trop longue, meme avec le petit lanceur prive.' }
    $command='"'+$Executable+'" '+$Arguments
    # WScript hides the child from its creation; VB string quotes must be doubled.
    $content=@('Option Explicit', 'Dim shell', 'Set shell = CreateObject("WScript.Shell")',
        ('shell.Run "'+$command.Replace('"','""')+'", 0, False')) -join "`r`n"
    [pscustomobject]@{Path=$LauncherPath;HostPath=$hostPath;RunCommand=$runCommand;Content=$content}
}

function Get-LimitedProcessImage([int]$ProcessId) {
    # CIM may hide ExecutablePath for the existing Elgato process. Limited-query
    # rights expose only its image path and do not request injection privileges.
    if (-not ('SignalRGBStartup.ProcessImage' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
namespace SignalRGBStartup {
    public static class ProcessImage {
        [DllImport("kernel32.dll", SetLastError=true)]
        static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        static extern bool QueryFullProcessImageNameW(IntPtr process, uint flags, StringBuilder image, ref uint size);
        [DllImport("kernel32.dll")]
        static extern bool CloseHandle(IntPtr handle);
        public static string Read(uint pid) {
            IntPtr handle = OpenProcess(0x1000, false, pid);
            if (handle == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            try {
                uint size=32768;
                var image=new StringBuilder((int)size);
                if (!QueryFullProcessImageNameW(handle, 0, image, ref size))
                    throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                return image.ToString();
            } finally { CloseHandle(handle); }
        }
    }
}
'@
    }
    [SignalRGBStartup.ProcessImage]::Read([uint32]$ProcessId)
}

function Read-StartupConfig([string]$Path) {
    $config = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($config.schema_version -ne 1) { throw 'Version de configuration inconnue.' }
    foreach ($pair in @(@($config,'python'), @($config.govee,'directory'), @($config.govee,'python'),
        @($config.govee,'config_file'), @($config.nvidia,'directory'), @($config.nvidia,'runtime_directory'),
        @($config.streamdeck,'directory'), @($config.streamdeck,'runtime_directory'),
        @($config.streamdeck,'venv_directory'), @($config.streamdeck,'elgato_directory'))) {
        $value = [Environment]::ExpandEnvironmentVariables([string]$pair[0].($pair[1]))
        if (-not [IO.Path]::IsPathRooted($value) -or $value.Contains('"') -or $value.Contains("`n")) {
            throw ('Chemin absolu invalide : ' + $pair[1])
        }
        $pair[0].($pair[1]) = [IO.Path]::GetFullPath($value)
    }
    if ($config.streamdeck.plugin_directory) {
        $config.streamdeck.plugin_directory = [Environment]::ExpandEnvironmentVariables($config.streamdeck.plugin_directory)
        if (-not [IO.Path]::IsPathRooted($config.streamdeck.plugin_directory) -or $config.streamdeck.plugin_directory.Contains('"')) {
            throw 'Repertoire des plugins invalide.'
        }
    }
    return $config
}

function Get-BridgeDefinitions($Config) {
    @(
        [pscustomobject]@{Name='govee'; Directory=$Config.govee.directory; Entry='bridge.py'; Protocol='UDP'; Port=47684;
            RunFile=($Config.govee.config_file+'.run.json'); PidKey='pid'; TimeKey='processStartedUtc';
            StartArgs=@('-ConfigFile',$Config.govee.config_file,'-Python',$Config.govee.python,'-Background');
            StopArgs=@('-ConfigFile',$Config.govee.config_file)},
        [pscustomobject]@{Name='nvidia'; Directory=$Config.nvidia.directory; Entry='gpu_bridge.py'; Protocol='UDP'; Port=47687;
            RunFile=(Join-Path $Config.nvidia.runtime_directory 'run.json'); PidKey='pid'; TimeKey='startedUtc';
            StartArgs=@('-Python',$Config.python,'-RuntimeDirectory',$Config.nvidia.runtime_directory);
            StopArgs=@('-RuntimeDirectory',$Config.nvidia.runtime_directory)},
        [pscustomobject]@{Name='streamdeck'; Directory=$Config.streamdeck.directory; Entry='background_api.py'; Protocol='TCP'; Port=47686;
            RunFile=(Join-Path $Config.streamdeck.runtime_directory 'launcher.json'); PidKey='runner_pid'; TimeKey='';
            StartArgs=@('-Python',$Config.python,'-VenvDirectory',$Config.streamdeck.venv_directory,'-RuntimeDirectory',$Config.streamdeck.runtime_directory);
            StopArgs=@('-RuntimeDirectory',$Config.streamdeck.runtime_directory)}
    )
}

function Test-StartupFiles($Config) {
    $required = @($Config.python, $Config.govee.python, $Config.govee.config_file,
        (Join-Path $Config.streamdeck.venv_directory 'Scripts\python.exe'))
    foreach ($bridge in (Get-BridgeDefinitions $Config)) {
        $required += (Join-Path $bridge.Directory 'Start-Bridge.ps1'), (Join-Path $bridge.Directory 'Stop-Bridge.ps1'), (Join-Path $bridge.Directory $bridge.Entry)
    }
    foreach ($path in $required) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw ('Fichier requis absent : ' + $path) }
    }
}

function Get-RetryDelay([int]$Failures) {
    # Three quick attempts, then one retry per five minutes. No busy restart loop.
    if ($Failures -le 1) { return 5 }
    if ($Failures -eq 2) { return 15 }
    if ($Failures -eq 3) { return 60 }
    return 300
}

function Get-BridgeDecision($Observation, [datetime]$Now, [datetime]$NextAttempt) {
    if ($Observation.PortOpen) { return 'running' }
    if ($Observation.RunnerAlive -or $Observation.LauncherAlive) { return 'waiting-process' }
    if ($Observation.Name -eq 'streamdeck') {
        if ($Observation.ElgatoCount -ne 1) { return 'waiting-elgato' }
        if (-not $Observation.BuildSupported) { return 'unsupported-elgato' }
    }
    if ($Now -lt $NextAttempt) { return 'backoff' }
    return 'start'
}

function Get-ExpectedStreamHashes([string]$ScriptPath) {
    # Read constants only: never execute Python to discover the allowlist.
    $source = Get-Content -LiteralPath $ScriptPath -Raw
    $block = [regex]::Match($source, '(?s)HASHES\s*=\s*\{(.*?)\}')
    if (-not $block.Success) { throw 'Allowlist Elgato absente du pont.' }
    $result = @{}
    foreach ($name in @('StreamDeck.exe','Qt6Gui.dll','Qt6Core.dll')) {
        $pattern = '["'']' + [regex]::Escape($name) + '["'']\s*:\s*["'']([A-Fa-f0-9]{64})["'']'
        $match = [regex]::Match($block.Groups[1].Value, $pattern)
        if (-not $match.Success) { throw ('Empreinte attendue absente : ' + $name) }
        $result[$name] = $match.Groups[1].Value.ToUpperInvariant()
    }
    return $result
}

function Get-StartupSha256([string]$Path) {
    # Windows PowerShell can inherit a PowerShell 7 PSModulePath. Hash directly
    # through .NET so the build guard never depends on Get-FileHash autoload.
    $stream = $null
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($Path)
        return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '')
    } finally {
        if ($stream) { $stream.Dispose() }
        $algorithm.Dispose()
    }
}

function Get-StreamBuild($Config) {
    $script = Join-Path $Config.streamdeck.directory 'background_api.py'
    $expected = Get-ExpectedStreamHashes $script
    $fingerprint = @((Get-StartupSha256 $script))
    $supported = $true
    foreach ($name in ($expected.Keys | Sort-Object)) {
        $path = Join-Path $Config.streamdeck.elgato_directory $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { $supported=$false; $fingerprint += ($name+':missing'); continue }
        $actual = Get-StartupSha256 $path
        $fingerprint += ($name+':'+$actual)
        if ($actual -ne $expected[$name]) { $supported = $false }
    }
    [pscustomobject]@{Supported=$supported; Fingerprint=($fingerprint -join '|')}
}

function Get-StreamFileStamp($Config) {
    $paths = @((Join-Path $Config.streamdeck.directory 'background_api.py'))
    $paths += @('StreamDeck.exe','Qt6Gui.dll','Qt6Core.dll') | ForEach-Object { Join-Path $Config.streamdeck.elgato_directory $_ }
    (@($paths | ForEach-Object {
        $item = Get-Item -LiteralPath $_ -ErrorAction SilentlyContinue
        if ($item) { $_+':'+$item.Length+':'+$item.LastWriteTimeUtc.Ticks } else { $_+':missing' }
    }) -join '|')
}

function Test-BridgePort($Bridge) {
    if ($Bridge.Protocol -eq 'TCP') {
        return [bool](Get-NetTCPConnection -LocalPort $Bridge.Port -State Listen -ErrorAction SilentlyContinue)
    }
    return [bool](Get-NetUDPEndpoint -LocalPort $Bridge.Port -ErrorAction SilentlyContinue)
}

function Get-BridgeRunner($Bridge) {
    if (-not (Test-Path -LiteralPath $Bridge.RunFile)) { return $null }
    try {
        $metadata = Get-Content -LiteralPath $Bridge.RunFile -Raw | ConvertFrom-Json
        $process = Get-Process -Id ([int]$metadata.($Bridge.PidKey)) -ErrorAction SilentlyContinue
        if (-not $process) { return $null }
        if ($Bridge.TimeKey) {
            if ($process.StartTime.ToUniversalTime().Ticks -ne ([datetime]$metadata.($Bridge.TimeKey)).ToUniversalTime().Ticks) { return $null }
        } else {
            $record = Get-CimInstance Win32_Process -Filter ('ProcessId='+$process.Id) -ErrorAction Stop
            if ($record.CommandLine -notmatch '(?i)background_api\.py') { return $null }
        }
        return $process
    } catch { return $null }
}

function Start-BridgeLauncher($Bridge, [string]$Operation, [string]$Runtime, $Config) {
    $path = Join-Path $Bridge.Directory ($Operation+'-Bridge.ps1')
    $arguments = @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$path)
    if ($Operation -eq 'Start') {
        $arguments += $Bridge.StartArgs
        if ($Bridge.Name -eq 'streamdeck' -and $Config.streamdeck.plugin_directory) {
            $arguments += @('-SignalRGBPluginDirectory',$Config.streamdeck.plugin_directory)
        }
    } else { $arguments += $Bridge.StopArgs }
    # Windows filenames cannot contain double quotes; every argument is quoted.
    $quoted = @($arguments | ForEach-Object { '"'+[string]$_+'"' })
    $suffix = $Bridge.Name+'-'+$Operation.ToLowerInvariant()
    $process = Start-Process -FilePath (Get-WindowsPowerShell) -ArgumentList $quoted -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $Runtime ($suffix+'.stdout.log')) `
        -RedirectStandardError (Join-Path $Runtime ($suffix+'.stderr.log'))
    # Windows PowerShell 5.1 can otherwise lose ExitCode after the PID exits.
    # Acquire and retain the native handle while the launcher is still alive.
    [void]$process.Handle
    return $process
}

function Get-LauncherExitCode($Process) {
    if (-not $Process.HasExited) { throw 'Le lanceur est encore actif.' }
    # Flush redirected output and refresh the exit information on the held handle.
    $Process.WaitForExit()
    $Process.Refresh()
    if ($null -ne $Process.ExitCode) { return [int]$Process.ExitCode }
    return $null
}

function Stop-ConfiguredBridges($Config, [string]$Runtime) {
    $allStopped = $true
    foreach ($bridge in (Get-BridgeDefinitions $Config)) {
        if (-not (Get-BridgeRunner $bridge)) { continue }
        try {
            $launcher = Start-BridgeLauncher $bridge 'Stop' $Runtime $Config
            if (-not $launcher.WaitForExit(20000)) { $allStopped=$false; continue }
            $exitCode=Get-LauncherExitCode $launcher
            # Some launchers only create a marker. Give the bridge its cleanup window.
            $deadline = [datetime]::UtcNow.AddSeconds(20)
            while ((Get-BridgeRunner $bridge) -and [datetime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 250 }
            if ($null -eq $exitCode) {
                ('Code de sortie indisponible pour '+$bridge.Name+' : nettoyage non confirme.') |
                    Add-Content -LiteralPath (Join-Path $Runtime 'stop-warning.log') -Encoding UTF8
                $allStopped=$false
            } elseif ((Get-BridgeRunner $bridge) -or $exitCode -ne 0) { $allStopped = $false }
            $launcher.Dispose()
        } catch { $allStopped=$false }
    }
    return $allStopped
}
