@echo off
REM Test runner script for AI Orchestrator (Windows)
REM Usage: scripts\run-tests.bat [options]

setlocal enabledelayedexpansion

REM Colors (Windows 10+)
for /F "tokens=1,2 delims=#" %%a in ('"prompt #$H#$E# & echo on & for %%b in (1) do rem"') do (
  set "DEL=%%a"
  set "COLOR_GREEN=%%b[32m"
  set "COLOR_RED=%%b[31m"
  set "COLOR_YELLOW=%%b[33m"
  set "COLOR_RESET=%%b[0m"
)

REM Default values
set TEST_TYPE=all
set VERBOSITY=-v
set COVERAGE=false
set KEYWORD=

REM Parse arguments
:parse_args
if "%~1"=="" goto :end_parse_args
if "%~1"=="-h" goto :help
if "%~1"=="--help" goto :help
if "%~1"=="-t" (set TEST_TYPE=%~2 & shift & shift & goto :parse_args)
if "%~1"=="--type" (set TEST_TYPE=%~2 & shift & shift & goto :parse_args)
if "%~1"=="-v" (set VERBOSITY=-v & shift & goto :parse_args)
if "%~1"=="--verbose" (set VERBOSITY=-v & shift & goto :parse_args)
if "%~1"=="-q" (set VERBOSITY=-q & shift & goto :parse_args)
if "%~1"=="--quiet" (set VERBOSITY=-q & shift & goto :parse_args)
if "%~1"=="-c" (set COVERAGE=true & shift & goto :parse_args)
if "%~1"=="--coverage" (set COVERAGE=true & shift & goto :parse_args)
if "%~1"=="-k" (set KEYWORD=%~2 & shift & shift & goto :parse_args)

goto :main

:help
echo AI Orchestrator Test Runner (Windows)
echo.
echo Usage: scripts\run-tests.bat [options]
echo.
echo Options:
echo     -h, --help          Show this help message
echo     -t, --type TYPE     Test type: unit, e2e, integration, all ^(default: all^)
echo     -v, --verbose       Verbose output
echo     -q, --quiet         Quiet mode
echo     -c, --coverage      Generate coverage report
echo     -k KEYWORD          Run only tests matching keyword
echo.
echo Examples:
echo     scripts\run-tests.bat                          REM Run all tests
echo     scripts\run-tests.bat -t e2e                   REM Run only E2E tests
echo     scripts\run-tests.bat -t unit --coverage       REM Run unit tests with coverage
echo     scripts\run-tests.bat -k "test_clone"          REM Run tests matching keyword
goto :eof

:main
echo %COLOR_GREEN%==================================%COLOR_RESET%
echo %COLOR_GREEN%AI Orchestrator Test Runner%COLOR_RESET%
echo %COLOR_GREEN%==================================%COLOR_RESET%
echo.

REM Check prerequisites
echo %COLOR_GREEN%Checking prerequisites...%COLOR_RESET%
python --version >nul 2>&1
if errorlevel 1 (
    echo %COLOR_RED%Python is not installed%COLOR_RESET%
    exit /b 1
)

python -c "import pytest" >nul 2>&1
if errorlevel 1 (
    echo %COLOR_YELLOW%pytest is not installed. Installing dependencies...%COLOR_RESET%
    uv pip install -e ".[dev]" 2>nul || pip install -e ".[dev]"
)

echo %COLOR_GREEN%Prerequisites check passed%COLOR_RESET%
echo.

REM Setup test environment
echo %COLOR_GREEN%Setting up test environment...%COLOR_RESET%
if not exist .test_data mkdir .test_data

set DATABASE_URL=sqlite+aiosqlite:///./.test_data/test_orchestrator.db
set REDIS_URL=redis://localhost:6379
set TELEGRAM_BOT_TOKEN=test_token
set TELEGRAM_OWNER_ID=123456789
set GITHUB_TOKEN=test_token
set GITHUB_WEBHOOK_SECRET=test_secret
set IDLE_TIMEOUT=2
set MAX_CONCURRENT_INSTANCES=2

REM Clean previous test artifacts
if exist .test_data\* del /q .test_data\*
if exist %TEMP%\test_workspaces rmdir /s /q %TEMP%\test_workspaces
mkdir %TEMP%\test_workspaces

echo %COLOR_GREEN%Test environment ready%COLOR_RESET%
echo.

REM Determine test paths
set TEST_PATHS=tests\
if "%TEST_TYPE%"=="unit" set TEST_PATHS=tests\ --ignore=tests\e2e
if "%TEST_TYPE%"=="e2e" set TEST_PATHS=tests\e2e\
if "%TEST_TYPE%"=="integration" set TEST_PATHS=tests\e2e\test_integration.py

REM Build pytest arguments
set PYTEST_ARGS=%VERBOSITY%
if not "%KEYWORD%"=="" set PYTEST_ARGS=%PYTEST_ARGS% -k %KEYWORD%
if "%COVERAGE%"=="true" set PYTEST_ARGS=%PYTEST_ARGS% --cov=app --cov-report=term-missing --cov-report=html:htmlcov

REM Run tests
echo %COLOR_GREEN%Running %TEST_TYPE% tests...%COLOR_RESET%
echo %COLOR_GREEN%Test paths: %TEST_PATHS%%COLOR_RESET%

python -m pytest %TEST_PATHS% %PYTEST_ARGS%
if errorlevel 1 (
    echo.
    echo %COLOR_RED%==================================%COLOR_RESET%
    echo %COLOR_RED%Some tests failed%COLOR_RESET%
    echo %COLOR_RED%==================================%COLOR_RESET%
    goto :cleanup
)

echo.
echo %COLOR_GREEN%==================================%COLOR_RESET%
echo %COLOR_GREEN%All tests passed!%COLOR_RESET%
echo %COLOR_GREEN%==================================%COLOR_RESET%

if "%COVERAGE%"=="true" (
    echo %COLOR_GREEN%Coverage report generated in htmlcov\%COLOR_RESET%
)

:cleanup
echo.
echo %COLOR_GREEN%Cleaning up test environment...%COLOR_RESET%
if exist .test_data rmdir /s /q .test_data
if exist %TEMP%\test_workspaces rmdir /s /q %TEMP%\test_workspaces
if exist __pycache__ rmdir /s /q __pycache__
if exist app\__pycache__ rmdir /s /q app\__pycache__

echo %COLOR_GREEN%Cleanup complete%COLOR_RESET%

endlocal
exit /b 0
