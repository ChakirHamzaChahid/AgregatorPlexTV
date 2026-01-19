param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

$Colors = @{
    'Header'  = 'Cyan'
    'Success' = 'Green'
    'Warning' = 'Yellow'
    'Error'   = 'Red'
    'Info'    = 'Cyan'
    'Divider' = 'DarkGray'
}

function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 63) -ForegroundColor $Colors.Divider
    Write-Host $Text -ForegroundColor $Colors.Header
    Write-Host ("=" * 63) -ForegroundColor $Colors.Divider
    Write-Host ""
}

function Write-Success {
    param([string]$Text)
    Write-Host "[OK] $Text" -ForegroundColor $Colors.Success
}

function Write-Info {
    param([string]$Text)
    Write-Host "[INFO] $Text" -ForegroundColor $Colors.Info
}

function Write-Warning {
    param([string]$Text)
    Write-Host "[WARN] $Text" -ForegroundColor $Colors.Warning
}

function Write-ErrorMsg {
    param([string]$Text)
    Write-Host "[ERROR] $Text" -ForegroundColor $Colors.Error
}

function Test-PyTest {
    try {
        $result = python -m pytest --version 2>&1
        Write-Success "pytest found: $result"
    }
    catch {
        Write-ErrorMsg "pytest not installed!"
        Write-Host ""
        Write-Host "Install: pip install -r requirements-test.txt"
        Write-Host ""
        exit 1
    }
}

function Invoke-FastTests {
    Write-Header "Running FAST TESTS (exclude slow)"
    & python -m pytest tests/ -m "not slow" -v --tb=short
    return $LASTEXITCODE
}

function Invoke-AllTests {
    Write-Header "Running ALL TESTS"
    & python -m pytest tests/ -v --tb=short
    return $LASTEXITCODE
}

function Invoke-CoverageTests {
    Write-Header "Running COVERAGE REPORT"
    & python -m pytest tests/ `
        --cov=app `
        --cov-report=html `
        --cov-report=term-missing `
        -v
    
    $exitCode = $LASTEXITCODE
    Write-Success "Report generated: htmlcov/index.html"
    return $exitCode
}

function Invoke-DebugTests {
    Write-Header "Running DEBUG MODE (verbose + logs)"
    & python -m pytest tests/ -vv -s --tb=long --log-cli-level=DEBUG
    return $LASTEXITCODE
}

function Invoke-IntegrationTests {
    Write-Header "Running INTEGRATION TESTS"
    & python -m pytest tests/test_integration.py -v --tb=short
    return $LASTEXITCODE
}

function Invoke-EndpointsTests {
    Write-Header "Running ENDPOINTS TESTS"
    & python -m pytest tests/test_api_endpoints.py -v --tb=short
    return $LASTEXITCODE
}

function Invoke-MoviesTests {
    Write-Header "Running MOVIES TESTS"
    & python -m pytest tests/test_api_movies.py -v --tb=short
    return $LASTEXITCODE
}

function Invoke-StreamingTests {
    Write-Header "Running STREAMING TESTS"
    & python -m pytest tests/test_api_streaming.py -v --tb=short
    return $LASTEXITCODE
}

function Invoke-SingleTest {
    param([string]$TestPath)
    
    if ([string]::IsNullOrWhiteSpace($TestPath)) {
        Write-ErrorMsg "Specify a test to run"
        Write-Host ""
        Write-Host "Example: .\test-runner.ps1 single tests/test_api_endpoints.py::TestGetServers"
        Write-Host ""
        exit 1
    }
    
    Write-Header "Running SINGLE TEST"
    & python -m pytest $TestPath -vv --tb=short
    return $LASTEXITCODE
}

function Show-Help {
    Write-Host ""
    Write-Host "PlexHub Test Runner (PowerShell)" -ForegroundColor $Colors.Header
    Write-Host ""
    Write-Host "Usage: .\test-runner.ps1 [option] [test_path]" -ForegroundColor $Colors.Info
    Write-Host ""
    
    Write-Host "Options:" -ForegroundColor $Colors.Header
    Write-Host "    (default)      Fast tests (exclude slow tests)"
    Write-Host "    all            All tests (including slow)"
    Write-Host "    coverage       With coverage report HTML"
    Write-Host "    debug          Debug mode (verbose + logs)"
    Write-Host "    integration    Integration tests only"
    Write-Host "    endpoints      Endpoints tests only"
    Write-Host "    movies         Movies tests only"
    Write-Host "    streaming      Streaming tests only"
    Write-Host "    single TEST    Run specific test"
    Write-Host "    help           Show this help"
    Write-Host ""
    
    Write-Host "Examples:" -ForegroundColor $Colors.Header
    Write-Host "    .\test-runner.ps1"
    Write-Host "    .\test-runner.ps1 coverage"
    Write-Host "    .\test-runner.ps1 single tests/test_api_endpoints.py::TestGetServers"
    Write-Host ""
}

try {
    Test-PyTest
    
    $mode = if ($Arguments.Count -gt 0) { $Arguments[0] } else { "fast" }
    
    $exitCode = 0
    
    switch ($mode.ToLower()) {
        "fast"        { $exitCode = Invoke-FastTests }
        "all"         { $exitCode = Invoke-AllTests }
        "coverage"    { $exitCode = Invoke-CoverageTests }
        "debug"       { $exitCode = Invoke-DebugTests }
        "integration" { $exitCode = Invoke-IntegrationTests }
        "endpoints"   { $exitCode = Invoke-EndpointsTests }
        "movies"      { $exitCode = Invoke-MoviesTests }
        "streaming"   { $exitCode = Invoke-StreamingTests }
        "single"      { 
            $testPath = if ($Arguments.Count -gt 1) { $Arguments[1] } else { $null }
            $exitCode = Invoke-SingleTest -TestPath $testPath
        }
        "help"        { Show-Help }
        "-h"          { Show-Help }
        "--help"      { Show-Help }
        default       {
            Write-ErrorMsg "Unknown option: $mode"
            Show-Help
            exit 1
        }
    }
    
    exit $exitCode
}
catch {
    Write-ErrorMsg "Error: $($_.Exception.Message)"
    exit 1
}
