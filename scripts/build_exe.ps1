param(
    [switch]$SkipWebBuild,
    [switch]$SkipPyInstaller,
    [switch]$CopyModels
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$WebDir = Join-Path $ProjectRoot "web"
$WebDist = Join-Path $WebDir "dist"
$SpecPath = Join-Path $ProjectRoot "packaging\ElectronicRecognition.spec"
$ReleaseDir = Join-Path $ProjectRoot "dist\ElectronicRecognition"

function Copy-Directory($Source, $Destination) {
    if (Test-Path $Source) {
        if (Test-Path $Destination) {
            $ResolvedDestination = (Resolve-Path $Destination).Path
            $ResolvedRelease = (Resolve-Path $ReleaseDir).Path
            if (-not $ResolvedDestination.StartsWith($ResolvedRelease, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to remove a path outside the release directory: $ResolvedDestination"
            }
            Remove-Item -LiteralPath $Destination -Recurse -Force
        }
        New-Item -ItemType Directory -Force (Split-Path $Destination -Parent) | Out-Null
        Copy-Item $Source $Destination -Recurse -Force
    }
}

function Assert-PythonModule($ModuleName, $InstallHint) {
    python -c "import $ModuleName" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "$ModuleName is not installed in the current Python environment. Install it first: $InstallHint"
    }
}

function Invoke-Checked($Description, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

Push-Location $ProjectRoot
try {
    if (-not $SkipWebBuild) {
        Push-Location $WebDir
        try {
            Invoke-Checked "Frontend build" { npm run build }
        }
        finally {
            Pop-Location
        }
    }

    if (-not (Test-Path (Join-Path $WebDist "index.html"))) {
        throw "Frontend build output not found: $WebDist"
    }

    if (-not $SkipPyInstaller) {
        Assert-PythonModule "PyInstaller" 'python -m pip install -e ".[build]"'
        Invoke-Checked "PyInstaller build" { python -m PyInstaller $SpecPath --noconfirm --clean }
    }

    if (-not (Test-Path $ReleaseDir)) {
        throw "PyInstaller output not found: $ReleaseDir"
    }

    Copy-Directory $WebDist (Join-Path $ReleaseDir "web_dist")

    New-Item -ItemType Directory -Force -Path @(
        (Join-Path $ReleaseDir "data"),
        (Join-Path $ReleaseDir "result"),
        (Join-Path $ReleaseDir "logs")
    ) | Out-Null

    Copy-Directory (Join-Path $ProjectRoot "data\index") (Join-Path $ReleaseDir "data\index")
    New-Item -ItemType Directory -Force (Join-Path $ReleaseDir "data\search") | Out-Null
    $DemoQueries = Join-Path $ProjectRoot "data\search\demo_queries.json"
    if (Test-Path $DemoQueries) {
        Copy-Item $DemoQueries (Join-Path $ReleaseDir "data\search\demo_queries.json") -Force
    }
    if ($CopyModels) {
        Copy-Directory (Join-Path $ProjectRoot "data\models") (Join-Path $ReleaseDir "data\models")
    }
    if (Test-Path (Join-Path $ProjectRoot ".env")) {
        Copy-Item (Join-Path $ProjectRoot ".env") (Join-Path $ReleaseDir ".env") -Force
    }

    Write-Host "Build complete:"
    Write-Host "  $ReleaseDir\ElectronicRecognition.exe"
}
finally {
    Pop-Location
}
