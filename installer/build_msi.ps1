param(
    [switch]$Clean,
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)),
    [string]$WixVersion = "3.14.1"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Get-CommandPath {
    param([string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    return $null
}

function Get-AppVersion {
    param([string]$ProjectRoot)

    $versionFile = Join-Path $ProjectRoot "src\version.py"
    $content = Get-Content -Raw $versionFile
    $match = [regex]::Match($content, 'APP_VERSION\s*=\s*"([^"]+)"')
    if (-not $match.Success) {
        throw "Could not determine APP_VERSION from $versionFile"
    }

    return $match.Groups[1].Value
}

function Get-PortablyInstalledWixRoot {
    $baseDir = Join-Path $env:LOCALAPPDATA "iCloudSynoSync\wix"
    $candidate = Join-Path $baseDir $WixVersion
    if ((Test-Path (Join-Path $candidate "candle.exe")) -and (Test-Path (Join-Path $candidate "light.exe"))) {
        return $candidate
    }

    return $null
}

function Ensure-WixPortableTools {
    param([string]$BaseDir)

    $toolsRoot = Join-Path $BaseDir $WixVersion
    $candlePath = Join-Path $toolsRoot "candle.exe"
    $lightPath = Join-Path $toolsRoot "light.exe"

    if ((Test-Path $candlePath) -and (Test-Path $lightPath)) {
        return $toolsRoot
    }

    New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null

    $zipPath = Join-Path $BaseDir "wix-$WixVersion-binaries.zip"
    $downloadUrl = "https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip"

    Write-Step "Downloading portable WiX $WixVersion binaries"
    Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath

    Write-Step "Extracting portable WiX $WixVersion binaries"
    Expand-Archive -Path $zipPath -DestinationPath $toolsRoot -Force

    $resolvedCandle = Get-ChildItem -Path $toolsRoot -Filter candle.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    $resolvedLight = Get-ChildItem -Path $toolsRoot -Filter light.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1

    if (-not $resolvedCandle -or -not $resolvedLight) {
        throw "Portable WiX binaries were downloaded but candle.exe/light.exe were not found."
    }

    return $resolvedCandle.Directory.FullName
}

try {
    Set-Location $ProjectRoot

    $AppVersion = Get-AppVersion -ProjectRoot $ProjectRoot
    $InstallerVersion = if ($AppVersion -match '^\d+\.\d+\.\d+$') { "$AppVersion.0" } else { $AppVersion }

    $ExePath = Join-Path $ProjectRoot "dist\iCloudSynoSync.exe"
    $InstallerSource = Join-Path $ProjectRoot "installer\iCloudSynoSync.wxs"
    $InstallerOutputDir = Join-Path $ProjectRoot "dist\installer"
    $GeneratedInstallerSource = Join-Path $InstallerOutputDir "iCloudSynoSync.generated.wxs"
    $MsiPath = Join-Path $InstallerOutputDir "iCloudSynoSync.msi"
    $PortableWixRoot = $null

    if (-not (Test-Path $ExePath)) {
        throw "Missing executable at $ExePath. Run .\build_exe.ps1 first."
    }

    if ($Clean) {
        Write-Step "Cleaning previous MSI artifacts"
        Remove-Item -Force $MsiPath -ErrorAction SilentlyContinue
        Remove-Item -Force (Join-Path $InstallerOutputDir "iCloudSynoSync.wixobj") -ErrorAction SilentlyContinue
        Remove-Item -Force $GeneratedInstallerSource -ErrorAction SilentlyContinue
    }

    New-Item -ItemType Directory -Force -Path $InstallerOutputDir | Out-Null

    $escapedExePath = [System.Security.SecurityElement]::Escape($ExePath)
    $installerContent = Get-Content -Raw $InstallerSource
    $installerContent = $installerContent.Replace("__EXE_PATH__", $escapedExePath)
    $installerContent = $installerContent.Replace("__PRODUCT_VERSION__", $InstallerVersion)
    $installerContent | Set-Content -Encoding UTF8 $GeneratedInstallerSource

    $WixCommand = Get-CommandPath "wix"
    $CandleCommand = Get-CommandPath "candle.exe"
    $LightCommand = Get-CommandPath "light.exe"

    if (-not $WixCommand -and (-not $CandleCommand -or -not $LightCommand)) {
        $wixCacheRoot = Join-Path $env:LOCALAPPDATA "iCloudSynoSync\wix"
        New-Item -ItemType Directory -Force -Path $wixCacheRoot | Out-Null
        $PortableWixRoot = Ensure-WixPortableTools -BaseDir $wixCacheRoot
        $CandleCommand = Join-Path $PortableWixRoot "candle.exe"
        $LightCommand = Join-Path $PortableWixRoot "light.exe"
    }

    if ($WixCommand) {
        Write-Step "Building MSI with WiX v4 command line"
        & $WixCommand build $GeneratedInstallerSource -arch x64 -o $MsiPath
    }
    elseif ($CandleCommand -and $LightCommand) {
        Write-Step "Building MSI with WiX v3 candle/light"
        $WixObject = Join-Path $InstallerOutputDir "iCloudSynoSync.wixobj"
        & $CandleCommand -nologo -arch x64 -out $WixObject $GeneratedInstallerSource
        if ($LASTEXITCODE -ne 0) {
            throw "candle.exe failed while compiling $GeneratedInstallerSource"
        }

        & $LightCommand -nologo -spdb -sice:ICE91 -sice:ICE61 -out $MsiPath $WixObject
        if ($LASTEXITCODE -ne 0) {
            throw "light.exe failed while linking $WixObject"
        }
    }
    else {
        throw "WiX Toolset was not found and the portable fallback could not be prepared."
    }

    if (Test-Path $MsiPath) {
        Write-Host "`nMSI build successful: $MsiPath" -ForegroundColor Green
        exit 0
    }

    throw "MSI build completed but the expected file was not created at $MsiPath"
}
catch {
    Write-Host "`nMSI build failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}