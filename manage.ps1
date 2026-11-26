[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Install', 'Start', 'Stop', 'Status', 'Uninstall')]
    [string] $Action = 'Status',

    [string] $PythonPath = 'python'
)

$ErrorActionPreference = 'Stop'
$taskName = 'RnxRutrRandomBook'
$task = Get-ScheduledTask -TaskPath '\' -TaskName $taskName -ErrorAction SilentlyContinue

if ($Action -eq 'Install') {
    $pythonJson = & $PythonPath -c 'import json, sys; print(json.dumps(sys.executable)); sys.exit(sys.version_info < (3, 10))'
    if ($LASTEXITCODE -ne 0) {
        throw 'Python 3.10 or later is required. Use -PythonPath to specify python.exe.'
    }
    $pythonExe = ConvertFrom-Json -InputObject $pythonJson
    $pythonw = Join-Path (Split-Path -Parent $pythonExe) 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
        throw "pythonw.exe was not found beside $pythonExe. Use a complete Windows Python installation."
    }

    $entryPoint = Join-Path $PSScriptRoot 'book_service.py'
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $process = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}"' -f $entryPoint)
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

    if ($task -and $task.State -eq 'Running') {
        $task | Stop-ScheduledTask
    }
    $task = Register-ScheduledTask -TaskPath '\' -TaskName $taskName -Action $process `
        -Trigger $trigger -Principal $principal -Settings $settings `
        -Description 'Opens books from RuTracker and DjVu Online. Alt+T+A+G opens the DjVu Online tag catalog.' -Force
    $task | Start-ScheduledTask
    Write-Output 'Installed and started. Hotkeys: Ctrl+R+N+D, Ctrl+I+T, Ctrl+M+A+T, Ctrl+F+I+Z, Ctrl+F+I+L, Ctrl+R+E+L, Alt+R+N+D, Alt+I+T and Alt+T+A+G.'
    return
}

if (-not $task) {
    Write-Output 'RnxRutrRandomBook is not installed.'
    return
}

switch ($Action) {
    'Start' { $task | Start-ScheduledTask }
    'Stop' { $task | Stop-ScheduledTask }
    'Status' { $task | Select-Object TaskName, State }
    'Uninstall' {
        if ($task.State -eq 'Running') {
            $task | Stop-ScheduledTask
        }
        $task | Unregister-ScheduledTask -Confirm:$false
    }
}
