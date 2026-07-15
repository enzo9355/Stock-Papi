[CmdletBinding(SupportsShouldProcess)]
param(
  [string]$DataRoot = 'D:\AbsorbData',
  [ValidateSet('Saturday','Sunday')][string]$WeeklyDay = 'Saturday'
)
$ErrorActionPreference = 'Stop'
if ($DataRoot -ne 'D:\AbsorbData') { throw 'Data root is not allowlisted' }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-ScheduledTaskPrincipal -UserId $Identity.Name -LogonType Interactive -RunLevel Limited
$TaskWrapper = Join-Path $PSScriptRoot 'invoke_pipeline_task.ps1'
if (-not (Test-Path -LiteralPath $TaskWrapper -PathType Leaf)) { throw "Task wrapper not found: $TaskWrapper" }
$Definitions = @(
  @{ Name='ABSORB-TW-PostClose'; Job='TW-PostClose'; Time='17:10' },
  @{ Name='ABSORB-TW-PreMarket'; Job='TW-PreMarket'; Time='07:30' },
  @{ Name='ABSORB-FullBacktest'; Job='FullBacktest'; Time='22:30'; RepeatMinutes=1 },
  @{ Name='ABSORB-US-Daily'; Job='US-Daily'; Time='05:30' },
  @{ Name='ABSORB-WeeklyModel'; Job='WeeklyModel'; Time='18:00'; Days=$WeeklyDay },
  @{ Name='ABSORB-ReportUploadRecovery'; Job='ReportUploadRecovery'; Time='09:35' }
)
foreach ($Definition in $Definitions) {
  $Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$TaskWrapper`" -Job `"$($Definition.Job)`" -DataRoot `"$DataRoot`"" -WorkingDirectory $RepoRoot
  $At = [datetime]::ParseExact($Definition.Time, 'HH:mm', $null)
  $Trigger = if ($Definition.Days) {
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Definition.Days -At $At
  } elseif ($Definition.RepeatMinutes) {
    New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $Definition.RepeatMinutes)
  } else {
    New-ScheduledTaskTrigger -Daily -At $At
  }
  $Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 4) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10)
  $Settings.StartWhenAvailable = $true
  $Settings.WakeToRun = $true
  if ($PSCmdlet.ShouldProcess($Definition.Name, 'Register shadow pipeline task')) {
    Register-ScheduledTask -TaskName $Definition.Name -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
  }
}
