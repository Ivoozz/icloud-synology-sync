param(
    [switch]$Clean,
    [switch]$RecreateVenv,
    [string]$VenvDir = ".venv",
    [string]$PythonSelector = ""
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

try {
    $ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $ProjectRoot

    Write-Step "Building executable"
    $buildExeParams = @{}
    if ($Clean) { $buildExeParams["Clean"] = $true }
    if ($RecreateVenv) { $buildExeParams["RecreateVenv"] = $true }
    if ($VenvDir) { $buildExeParams["VenvDir"] = $VenvDir }
    if ($PythonSelector) { $buildExeParams["PythonSelector"] = $PythonSelector }
    & .\build_exe.ps1 @buildExeParams
    if ($LASTEXITCODE -ne 0) {
        throw "Executable build failed."
    }

    Write-Step "Building MSI installer"
    $installerParams = @{}
    if ($Clean) { $installerParams["Clean"] = $true }
    & .\installer\build_msi.ps1 @installerParams
    if ($LASTEXITCODE -ne 0) {
        throw "MSI build failed."
    }

    Write-Host "`nAll build artifacts were generated successfully." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "`nBuild-all failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}