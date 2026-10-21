# Windows PowerShell 5.1: encrypt with the current user's DPAPI profile.
param([Parameter(Mandatory=$true)][string]$ProjectRoot)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($ProjectRoot)
$folder = Join-Path $root 'secrets'
$destination = Join-Path $folder 'gemini.key'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
Write-Host ''
Write-Host 'Paste the Google AI Studio API key below. It will NOT be echoed.'
Write-Host 'Key is encrypted for your Windows account and saved ONLY on this PC.'
$key = Read-Host 'Gemini API key' -AsSecureString
if ($key.Length -lt 15) { throw 'API key appears too short. Nothing was saved.' }
$encrypted = ConvertFrom-SecureString -SecureString $key
Set-Content -LiteralPath $destination -Value $encrypted -Encoding ASCII
Write-Host 'Encrypted key saved to secrets/gemini.key. Do not share this file or your Windows profile.'
