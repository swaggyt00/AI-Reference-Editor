#Requires -Version 5.1
param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectRoot
)
$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath($ProjectRoot)
$bin = Join-Path $root 'tools\ffmpeg\bin'
$ffmpeg = Join-Path $bin 'ffmpeg.exe'
$ffprobe = Join-Path $bin 'ffprobe.exe'
if ((Test-Path -LiteralPath $ffmpeg) -and (Test-Path -LiteralPath $ffprobe)) {
    Write-Host 'FFmpeg already installed inside this project.'
    exit 0
}
$sourceUrl = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
$checksumUrl = $sourceUrl + '.sha256'
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ('refeditor-ffmpeg-' + [guid]::NewGuid().ToString('N'))
New-Item -Path $temp -ItemType Directory -Force | Out-Null
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $archive = Join-Path $temp 'ffmpeg-release-essentials.zip'
    $shaPath = Join-Path $temp 'ffmpeg-release-essentials.zip.sha256'
    Write-Host 'Downloading official FFmpeg essentials ZIP (about 110 MB)...'
    Invoke-WebRequest -Uri $sourceUrl -OutFile $archive -UseBasicParsing -TimeoutSec 600
    Write-Host 'Downloading official SHA-256 checksum...'
    Invoke-WebRequest -Uri $checksumUrl -OutFile $shaPath -UseBasicParsing -TimeoutSec 60
    $checksumText = [System.IO.File]::ReadAllText($shaPath)
    $match = [regex]::Match($checksumText, '(?i)[a-f0-9]{64}')
    if (-not $match.Success) { throw 'Unable to parse official SHA-256 checksum.' }
    $expected = $match.Value.ToLowerInvariant()
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -ne $actual) {
        throw 'FFmpeg downloaded archive checksum does not match official SHA-256!'
    }
    Write-Host 'SHA-256 verified. Extracting FFmpeg...'
    $unpack = Join-Path $temp 'unpacked'
    Expand-Archive -LiteralPath $archive -DestinationPath $unpack -Force
    $found = Get-ChildItem -LiteralPath $unpack -Filter 'ffmpeg.exe' -File -Recurse | Where-Object { $_.Directory.Name -eq 'bin' } | Select-Object -First 1
    if (-not $found) { throw 'Extracted ZIP did not contain bin/ffmpeg.exe.' }
    $probeSrc = Join-Path $found.Directory.FullName 'ffprobe.exe'
    if (-not (Test-Path -LiteralPath $probeSrc)) { throw 'Extracted ZIP did not contain bin/ffprobe.exe.' }
    New-Item -Path $bin -ItemType Directory -Force | Out-Null
    Copy-Item -LiteralPath $found.FullName -Destination $ffmpeg -Force
    Copy-Item -LiteralPath $probeSrc -Destination $ffprobe -Force
    & $ffmpeg -version | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) { throw 'Downloaded FFmpeg executable could not start.' }
    Write-Host 'FFmpeg is ready in tools/ffmpeg/bin, with no system-wide changes.'
    exit 0
}
catch {
    Write-Error ('FFmpeg installation failed: ' + $_.Exception.Message)
    exit 1
}
finally {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
