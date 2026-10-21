param([Parameter(Mandatory=$true)][string]$ProjectRoot)
$ErrorActionPreference = 'Stop'
$version = 'v22.16.0'
$package = "node-$version-win-x64.zip"
$root = [IO.Path]::GetFullPath($ProjectRoot)
$dest = Join-Path $root 'tools\node'
$node = Join-Path $dest 'node.exe'
if (Test-Path -LiteralPath $node) {
  Write-Host 'Local Node already installed.'; exit 0
}
$temp=Join-Path $env:TEMP ('refeditor-node-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp -Force | Out-Null
try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  $origin="https://nodejs.org/dist/$version"
  $zip=Join-Path $temp $package
  $checks=Join-Path $temp 'SHASUMS256.txt'
  Write-Host 'Downloading verified official Node.js ZIP (~30MB)...'
  Invoke-WebRequest -UseBasicParsing -Uri "$origin/$package" -OutFile $zip -TimeoutSec 600
  Invoke-WebRequest -UseBasicParsing -Uri "$origin/SHASUMS256.txt" -OutFile $checks -TimeoutSec 60
  $row=Get-Content $checks | Where-Object { $_ -match [regex]::Escape($package) } | Select-Object -First 1
  if (-not $row -or $row -notmatch '^(?<sha>[0-9a-f]{64})\s+') { throw 'Official Node checksum not found.' }
  $actual=(Get-FileHash -Algorithm SHA256 $zip).Hash.ToLowerInvariant()
  if ($actual -ne $Matches['sha'].ToLowerInvariant()) { throw 'Node.js archive SHA-256 mismatch.' }
  $unpack=Join-Path $temp 'unpacked'
  Expand-Archive $zip -DestinationPath $unpack -Force
  $folder=Join-Path $unpack "node-$version-win-x64"
  if (-not (Test-Path (Join-Path $folder 'npm.cmd'))) { throw 'Node distribution incomplete.' }
  New-Item -ItemType Directory -Path $dest -Force | Out-Null
  Copy-Item -Path (Join-Path $folder '*') -Destination $dest -Recurse -Force
  & $node --version
  if ($LASTEXITCODE -ne 0) { throw 'Node executable could not start.' }
  Write-Host 'Portable Node installed locally. No administrator rights needed.'
  exit 0
}
catch { Write-Error $_.Exception.Message; exit 1 }
finally { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
