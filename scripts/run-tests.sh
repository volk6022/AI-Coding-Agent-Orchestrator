#!/usr/bin/env bash
# Test runner script for AI Orchestrator
# Usage: ./scripts/run-tests.sh [options]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
TEST_TYPE="all"
VERBOSITY="-v"
COVERAGE=false
WATCH=false

# Helper functions
print_help() {
    cat << EOF
AI Orchestrator Test Runner

Usage: ./scripts/run-tests.sh [options]

Options:
    -h, --help          Show this help message
    -t, --type TYPE     Test type: unit, e2e, integration, all (default: all)
    -v, --verbose       Verbose output
    -q, --quiet         Quiet mode
    -c, --coverage      Generate coverage report
    -w, --watch         Watch mode (re-run on file changes)
    -k KEYWORD          Run only tests matching keyword

Examples:
    ./scripts/run-tests.sh                          # Run all tests
    ./scripts/run-tests.sh -t e2e                   # Run only E2E tests
    ./scripts/run-tests.sh -t unit --coverage       # Run unit tests with coverage
    ./scripts/run-tests.sh -k "test_clone"          # Run tests matching keyword
    ./scripts/run-tests.sh -t e2e -w                # Run E2E tests in watch mode

EOF
}

echo_info() {
    echo -e "${GREEN}$1${NC}"
}

echo_warn() {
    echo -e "${YELLOW}$1${NC}"
}

echo_error() {
    echo -e "${RED}$1${NC}"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            print_help
            exit 0
            ;;
        -t|--type)
            TEST_TYPE="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSITY="-v"
            shift
            ;;
        -q|--quiet)
            VERBOSITY="-q"
            shift
            ;;
        -c|--coverage)
            COVERAGE=true
            shift
            ;;
        -w|--watch)
            WATCH=true
            shift
            ;;
        -k)
            KEYWORD="$2"
            shift 2
            ;;
        *)
            echo_error "Unknown option: $1"
            print_help
            exit 1
            ;;
    esac
done

# Validate test type
if [[ ! "$TEST_TYPE" =~ ^(unit|e2e|integration|all)$ ]]; then
    echo_error "Invalid test type: $TEST_TYPE"
    echo_error "Valid types: unit, e2e, integration, all"
    exit 1
fi

# Check prerequisites
check_prerequisites() {
    echo_info "Checking prerequisites..."

    if ! command -v python &> /dev/null; then
        echo_error "Python is not installed"
        exit 1
    fi

    if ! command -v uv &> /dev/null; then
        echo_warn "uv is not installed. Consider installing it for better performance."
    fi

    if ! python -c "import pytest" &> /dev/null; then
        echo_warn "pytest is not installed. Installing dependencies..."
        if command -v uv &> /dev/null; then
            uv pip install -e ".[dev]"
        else
            pip install -e ".[dev]"
        fi
    fi

    echo_info "Prerequisites check passed"
}

# Setup test environment
setup_test_environment() {
    echo_info "Setting up test environment..."

    # Create test database directory if it doesn't exist
    mkdir -p .test_data

    # Set test-specific environment variables
    export DATABASE_URL="sqlite+aiosqlite:///./.test_data/test_orchestrator.db"
    export REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
    export TELEGRAM_BOT_TOKEN="test_token"
    export TELEGRAM_OWNER_ID="123456789"
    export GITHUB_TOKEN="test_token"
    export GITHUB_WEBHOOK_SECRET="test_secret"
    export IDLE_TIMEOUT="2"
    export MAX_CONCURRENT_INSTANCES="2"

    # Clean previous test artifacts
    rm -rf .test_data/*
    rm -rf /tmp/test_workspaces 2>/dev/null || true
    mkdir -p /tmp/test_workspaces

    echo_info "Test environment ready"
}

# Cleanup test environment
cleanup_test_environment() {
    echo_info "Cleaning up test environment..."

    rm -rf .test_data
    rm -rf /tmp/test_workspaces 2>/dev/null || true
    rm -rf __pycache__ 2>/dev/null || true
    rm -rf app/__pycache__ 2>/dev/null || true
    rm -rf app/*/__pycache__ 2>/dev/null || true
    rm -rf app/*/*/__pycache__ 2>/dev/null || true

    echo_info "Cleanup complete"
}

# Run tests
run_tests() {
    local test_args=()

    # Build pytest arguments
    if [[ "$VERBOSITY" == "-v" ]]; then
        test_args+=("-v")
    elif [[ "$VERBOSITY" == "-q" ]]; then
        test_args+=("-q")
    fi

    if [[ -n "$KEYWORD" ]]; then
        test_args+=("-k" "$KEYWORD")
    fi

    if [[ "$COVERAGE" == true ]]; then
        test_args+=("--cov=app" "--cov-report=term-missing" "--cov-report=html:htmlcov")
    fi

    # Determine test paths
    local test_paths=()

    case $TEST_TYPE in
        unit)
            test_paths=("tests/" "--ignore=tests/e2e")
            ;;
        e2e)
            test_paths=("tests/e2e/")
            ;;
        integration)
            test_paths=("tests/e2e/test_integration.py")
            ;;
        all)
            test_paths=("tests/")
            ;;
    esac

    # Run tests
    echo_info "Running $TEST_TYPE tests..."
    echo_info "Test paths: ${test_paths[*]}"

    if [[ "$WATCH" == true ]]; then
        # Install pytest-watch if not present
        if ! python -c "import pytest_watch" &> /dev/null; then
            echo_warn "Installing pytest-watch..."
            pip install pytest-watch
        fi
        ptw -- "${test_paths[@]}" "${test_args[@]}"
    else
        python -m pytest "${test_paths[@]}" "${test_args[@]}"
    fi
}

# Main execution
main() {
    echo_info "=================================="
    echo_info "AI Orchestrator Test Runner"
    echo_info "=================================="
    echo

    check_prerequisites
    echo

    setup_test_environment
    echo

    # Trap cleanup on exit
    trap cleanup_test_environment EXIT

    # Run tests
    if run_tests; then
        echo
        echo_info "=================================="
        echo_info "✅ All tests passed!"
        echo_info "=================================="

        if [[ "$COVERAGE" == true ]]; then
            echo_info "Coverage report generated in htmlcov/"
        fi

        exit 0
    else
        echo
        echo_error "=================================="
        echo_error "❌ Some tests failed"
        echo_error "=================================="
        exit 1
    fi
}

main
