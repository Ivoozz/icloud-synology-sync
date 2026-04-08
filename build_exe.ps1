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

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $FilePath $($Arguments -join ' ')"
    }
}

try {
    $ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $ProjectRoot

    Write-Step "Project root: $ProjectRoot"

    if ($Clean) {
        Write-Step "Cleaning previous build artifacts"
        Remove-Item -Recurse -Force "build" -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force "dist" -ErrorAction SilentlyContinue
        Remove-Item -Force "iCloudSynoSync.spec" -ErrorAction SilentlyContinue
    }

    if ($RecreateVenv -and (Test-Path $VenvDir)) {
        Write-Step "Removing existing virtual environment: $VenvDir"
        Remove-Item -Recurse -Force $VenvDir
    }

    if (-not (Test-Path $VenvDir)) {
        Write-Step "Creating virtual environment ($VenvDir)"
        $venvArgs = @()
        if ($PythonSelector -and $PythonSelector.Trim()) {
            $venvArgs += $PythonSelector
        }
        $venvArgs += @("-m", "venv", $VenvDir)
        Invoke-Checked -FilePath "py" -Arguments $venvArgs
    }

    $VenvPython = Join-Path $ProjectRoot "$VenvDir\Scripts\python.exe"
    if (-not (Test-Path $VenvPython)) {
        throw "Virtual environment Python not found at $VenvPython"
    }

    Write-Step "Upgrading pip"
    Invoke-Checked -FilePath $VenvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")

    Write-Step "Installing requirements"
    Invoke-Checked -FilePath $VenvPython -Arguments @("-m", "pip", "install", "-r", "requirements.txt")

    Write-Step "Running build script"
    Invoke-Checked -FilePath $VenvPython -Arguments @("build.py")

    $ExePath = Join-Path $ProjectRoot "dist\iCloudSynoSync.exe"
    if (Test-Path $ExePath) {
        Write-Host "`nBuild successful: $ExePath" -ForegroundColor Green
        exit 0
    }

    throw "Build script finished but expected executable not found at $ExePath"
}
catch {
    Write-Host "`nBuild failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
