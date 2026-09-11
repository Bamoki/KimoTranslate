<# KimoTranslate Windows build: GUI .exe + Updater .exe + (opcional) publish.
   Requiere: Windows x64, Python 3.11+ con tkinter, conexión a internet.
   Uso:
     powershell -ExecutionPolicy Bypass -File scripts\build_windows_gui.ps1
     powershell -ExecutionPolicy Bypass -File scripts\build_windows_gui.ps1 -Publish `
       -HubUrl http://192.168.1.20:8000 -HubUser admin -HubPassword $env:HUB_PASS
#>
param(
    [string]$HubUrl = "",
    [string]$HubUser = "",
    [string]$HubPassword = "",
    [switch]$Publish
)

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $MyInvocation.MyCommand.Path -Parent) -Parent
Set-Location $Root

# 1. Versión única desde src (NO duplicar).
$Version = (Select-String -Path "src/kimotranslate/__init__.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "KimoTranslate version: $Version"
$Version | Out-File -Encoding utf8 -NoNewline "build_version.txt"

# 2. PyInstaller (solo build-time; el .exe final no necesita Python).
python -c "import tkinter"  # falla si tkinter no está instalado
pip install --quiet pyinstaller
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
pyinstaller KimoTranslate.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

$GuiExe = "dist/KimoTranslate.exe"
$UpdExe = "dist/KimoTranslate-Updater.exe"
$GuiFinal = "dist/KimoTranslate-$Version.exe"
Copy-Item $GuiExe $GuiFinal -Force
$Sha = (Get-FileHash $GuiFinal -Algorithm SHA256).Hash.ToLower()
$Sha | Out-File -Encoding utf8 -NoNewline "$GuiFinal.sha256"
$Size = (Get-Item $GuiFinal).Length
Write-Host "EXE: $GuiFinal ($Size bytes) sha256=$Sha"
Write-Host "Updater: $UpdExe ($((Get-Item $UpdExe).Length) bytes)"

# 3. Smoke del updater (lógica pura, sin GUI): --help debe salir 0.
& $UpdExe --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "updater smoke failed" }

# 4. Publicación opcional en Raspberry-Hub (requiere sesión admin).
if ($Publish) {
    if (-not $HubUrl -or -not $HubUser -or -not $HubPassword) {
        throw "Publish necesita -HubUrl, -HubUser y -HubPassword"
    }
    $Session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $Login = Invoke-RestMethod "$HubUrl/api/auth/login" -Method Post -WebSession $Session `
        -ContentType "application/json" `
        -Body (@{username = $HubUser; password = $HubPassword} | ConvertTo-Json)
    $Form = @{file = Get-Item $GuiFinal; version = $Version}
    Invoke-RestMethod "$HubUrl/api/downloads/kimotranslate/publish" -Method Post `
        -WebSession $Session -Form $Form
    Write-Host "Published $Version to $HubUrl"
    Invoke-RestMethod "$HubUrl/api/downloads/kimotranslate/manifest.json" | ConvertTo-Json
}
