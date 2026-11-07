param([Parameter(Mandatory=$true)][string]$Version)
$ErrorActionPreference='Stop'
if($Version -notmatch '^v\d+\.\d+\.\d+$'){throw 'Invalid version'}
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskTarget=(Resolve-Path -LiteralPath (Join-Path $taskRoot "release\$Version")).Path
$taskStarted=Get-Date
Start-MpScan -ScanType CustomScan -ScanPath $taskTarget
$taskMatches=@(Get-MpThreatDetection | Where-Object { ($_.Resources -join ' ') -match [regex]::Escape($Version) } | Select-Object ThreatID,InitialDetectionTime,ActionSuccess,Resources)
$taskStatus=Get-MpComputerStatus
$taskExe=Join-Path $taskTarget '漫剧工坊\漫剧工坊.exe'
$taskInstaller=Join-Path $taskTarget ("漫剧工坊-安装程序-"+$Version.Substring(1)+'.exe')
$taskReport=[ordered]@{
 version=$Version; started=$taskStarted.ToString('o');completed=(Get-Date).ToString('o');scanPath=$taskTarget
 antivirusEnabled=$taskStatus.AntivirusEnabled;realTimeProtectionEnabled=$taskStatus.RealTimeProtectionEnabled
 signaturesUpdated=$taskStatus.AntivirusSignatureLastUpdated.ToString('o');matchingDetections=$taskMatches
 noMatchingDetection=($taskMatches.Count -eq 0)
 executableSha256=if(Test-Path -LiteralPath $taskExe){(Get-FileHash -LiteralPath $taskExe -Algorithm SHA256).Hash.ToLower()}else{$null}
 installerSha256=if(Test-Path -LiteralPath $taskInstaller){(Get-FileHash -LiteralPath $taskInstaller -Algorithm SHA256).Hash.ToLower()}else{$null}
}
$taskRecord=Join-Path $taskRoot "versions\$Version\defender-scan.json"
$taskReport | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $taskRecord -Encoding utf8
if(-not $taskReport.noMatchingDetection){throw 'Defender detected this candidate. Do not execute or deliver it.'}
if(-not $taskReport.executableSha256 -or -not $taskReport.installerSha256){throw 'Candidate files are missing'}
[pscustomobject]@{version=$Version;noMatchingDetection=$true;antivirusEnabled=$taskStatus.AntivirusEnabled;realTimeProtectionEnabled=$taskStatus.RealTimeProtectionEnabled} | ConvertTo-Json -Compress
