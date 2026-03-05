# E2E Testing Guide

This guide covers End-to-End (E2E) testing for the AI Orchestrator, including test scenarios, execution, and writing new tests.

## Table of Contents

- [Overview](#overview)
- [Test Architecture](#test-architecture)
- [Running E2E Tests](#running-e2e-tests)
- [Test Scenarios](#test-scenarios)
- [Writing New E2E Tests](#writing-new-e2e-tests)
- [Debugging Tests](#debugging-tests)
- [CI/CD Integration](#cicd-integration)

---

## Overview

E2E tests verify the complete flow of the AI Orchestrator from receiving a GitHub webhook to creating a Pull Request, including:

- ✅ Task execution flow
- ✅ Two-way GitHub sync (comments ↔ agent)
- ✅ Error handling and cleanup
- ✅ Timeout scenarios
- ✅ Concurrency control
- ✅ Database state persistence

---

## Test Architecture

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures and mocks
└── e2e/
    ├── __init__.py
    ├── test_flow.py         # Basic flow tests
    ├── test_failure_modes.py # Error handling tests
    └── test_integration.py  # Comprehensive integration tests
```

### Mock Components

E2E tests use mock implementations of external services:

| Component | Mock Class | Purpose |
|-----------|-----------|---------|
| Git | `MockGitCLIClient` | Simulates git operations |
| GitHub API | `MockGitHubAPIClient` | Tracks comments and PRs |
| OpenCode | `MockOpenCodeClient` | Simulates SSE event stream |
| Telegram | `MockTelegramNotifier` | Captures notifications |
| Database | `StateRepository` | Real DB with test database |

### Event Stream Simulation

Tests configure mock OpenCode clients with predefined event sequences:

```python
def create_standard_success_events() -> List[Dict[str, Any]]:
    return [
        {
            "event_name": "message_completed",
            "data": {
                "text": "I'll start working on this task.",
                "has_commands": False,
            },
        },
        {
            "event_name": "message_completed",
            "data": {
                "text": "I've implemented the feature. [TASK_COMPLETED]",
                "has_commands": False,
            },
        },
    ]
```

---

## Running E2E Tests

### Quick Start

```bash
# Run all E2E tests
./scripts/run-tests.sh -t e2e

# Or using pytest directly
pytest tests/e2e/ -v

# Run with coverage
pytest tests/e2e/ --cov=app --cov-report=term-missing
```

### Windows

```cmd
REM Run all E2E tests
scripts\run-tests.bat -t e2e

REM Run with coverage
scripts\run-tests.bat -t e2e -c
```

### Test Filters

```bash
# Run specific test class
pytest tests/e2e/test_integration.py::TestE2EFullFlow -v

# Run specific test
pytest tests/e2e/test_integration.py::TestE2EFullFlow::test_successful_task_execution -v

# Run tests matching keyword
pytest tests/e2e/ -k "timeout" -v

# Run tests matching multiple keywords
pytest tests/e2e/ -k "cleanup or failure" -v
```

### Environment Variables

```bash
# Test-specific settings (automatically set by test runner)
export DATABASE_URL="sqlite+aiosqlite:///./.test_data/test_orchestrator.db"
export IDLE_TIMEOUT=2  # Short timeout for tests
export MAX_CONCURRENT_INSTANCES=2
```

---

## Test Scenarios

### 1. Successful Task Execution

**File:** `test_integration.py::TestE2EFullFlow::test_successful_task_execution`

**Flow:**
1. GitHub webhook triggers task
2. Clone repository → Create branch
3. Spawn OpenCode server
4. Agent completes task → `[TASK_COMPLETED]`
5. Commit & push changes
6. Create Pull Request
7. Cleanup workspace

**Assertions:**
- ✅ Git clone called once
- ✅ Git push called once
- ✅ PR created
- ✅ Process killed
- ✅ Workspace cleaned
- ✅ DB status = `DONE`

---

### 2. Agent Asks Question

**File:** `test_integration.py::TestE2EFullFlow::test_agent_asks_question_then_completes`

**Flow:**
1. Agent sends message without completion marker
2. Message posted to GitHub as comment
3. Telegram notification sent
4. Agent receives reply (simulated)
5. Agent completes task

**Assertions:**
- ✅ Comment posted to GitHub
- ✅ Telegram message sent
- ✅ Task eventually completes

---

### 3. User Reply Injection

**File:** `test_integration.py::TestE2EFullFlow::test_task_with_user_reply_injection`

**Flow:**
1. Agent asks question
2. Task status → `WAITING_REPLY`
3. User comments on GitHub
4. Webhook routes reply to active session
5. Agent receives reply via `send_reply`

**Assertions:**
- ✅ Reply sent to correct session
- ✅ Session ID matches
- ✅ Port matches

---

### 4. Clone Failure

**File:** `test_integration.py::TestE2EFailureModes::test_clone_failure_triggers_cleanup`

**Flow:**
1. Git clone configured to fail
2. Exception raised
3. Cleanup triggered via `AsyncExitStack`

**Assertions:**
- ✅ Workspace cleaned up
- ✅ No orphaned processes

---

### 5. OpenCode Error

**File:** `test_integration.py::TestE2EFailureModes::test_error_event_triggers_cleanup`

**Flow:**
1. OpenCode emits error event
2. Error logged
3. Telegram notification sent
4. Cleanup triggered

**Assertions:**
- ✅ Process killed
- ✅ Workspace cleaned
- ✅ DB status = `FAILED`
- ✅ Telegram error notification

---

### 6. Idle Timeout

**File:** `test_integration.py::TestE2EFailureModes::test_idle_timeout_triggers_abort`

**Flow:**
1. Agent doesn't respond for `IDLE_TIMEOUT` seconds
2. `asyncio.timeout()` raises `TimeoutError`
3. GitHub comment posted
4. Task aborted

**Assertions:**
- ✅ Comment posted about timeout
- ✅ Telegram notification sent
- ✅ DB status = `ABORTED`

---

### 7. Concurrency Control

**File:** `test_integration.py::TestE2EConcurrency::test_concurrent_tasks_semaphore`

**Flow:**
1. Launch 3 concurrent tasks
2. Semaphore limits to `MAX_CONCURRENT_INSTANCES`
3. Tasks execute sequentially beyond limit

**Assertions:**
- ✅ Semaphore value restored after execution
- ✅ No race conditions

---

### 8. Database Persistence

**File:** `test_integration.py::TestE2EDatabasePersistence::test_task_state_persisted_throughout_lifecycle`

**Flow:**
1. Task created in DB
2. Port and session ID stored
3. Status updated throughout lifecycle
4. Final state persisted

**Assertions:**
- ✅ All fields correctly stored
- ✅ Status transitions correct

---

## Writing New E2E Tests

### Test Template

```python
import pytest
from app.domain.entities import IssueData
from tests.e2e.test_integration import (
    MockGitCLIClient,
    MockGitHubAPIClient,
    MockOpenCodeProcessManager,
    MockTelegramNotifier,
)

@pytest.mark.asyncio
async def test_custom_scenario(
    mock_git: MockGitCLIClient,
    mock_github: MockGitHubAPIClient,
    mock_oc_manager: MockOpenCodeProcessManager,
    mock_db: StateRepository,
    mock_telegram: MockTelegramNotifier,
):
    # 1. Arrange
    issue = IssueData(
        issue_number=999,
        repo_url="owner/repo",
        title="Custom Test",
        body="Test body",
        sender="test",
        owner="owner",
    )
    
    mock_oc_manager.configure_client_events([
        # Your custom event sequence
    ])
    
    # 2. Act
    from app.application.use_cases.execute_task import execute_coding_task
    
    await execute_coding_task(
        issue_data=issue,
        git=mock_git,
        github=mock_github,
        oc_manager=mock_oc_manager,
        db=mock_db,
        telegram=mock_telegram,
    )
    
    # 3. Assert
    assert len(mock_git.clone_calls) == 1
    # ... your assertions
```

### Best Practices

1. **Use Fixtures**: Leverage existing mocks from `conftest.py` and `test_integration.py`
2. **Descriptive Names**: Use clear test names that describe the scenario
3. **Arrange-Act-Assert**: Structure tests in three clear phases
4. **Isolated Tests**: Each test should be independent
5. **Short Timeouts**: Use `monkeypatch` to reduce timeouts for tests
6. **Clean Assertions**: Assert on specific behaviors, not implementation details

### Custom Event Streams

```python
def create_custom_events() -> List[Dict[str, Any]]:
    return [
        {
            "event_name": "message_completed",
            "data": {
                "text": "Starting work...",
                "has_commands": False,
            },
        },
        {
            "event_name": "tool_call",
            "data": {
                "tool": "run_command",
                "command": "npm test",
            },
        },
        {
            "event_name": "message_completed",
            "data": {
                "text": "Tests passed! [TASK_COMPLETED]",
                "has_commands": False,
            },
        },
    ]
```

---

## Debugging Tests

### Verbose Output

```bash
# Show print statements
pytest tests/e2e/test_integration.py -v -s

# Show local variables on failure
pytest tests/e2e/test_integration.py -l

# Stop on first failure
pytest tests/e2e/test_integration.py -x
```

### Logging

```python
import logging

@pytest.mark.asyncio
async def test_with_logging(caplog):
    caplog.set_level(logging.DEBUG)
    
    # Run test code
    
    # Assert logs
    assert "cloning_repo" in caplog.text
    assert "session_created" in caplog.text
```

### Debugger

```python
@pytest.mark.asyncio
async def test_debug():
    import pdb; pdb.set_trace()  # Breakpoint
    
    # ... test code
```

Run with:
```bash
pytest tests/e2e/test_integration.py::test_debug -s
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Install Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install uv
      uses: astral-sh/setup-uv@v3
    
    - name: Install dependencies
      run: uv pip install -e ".[dev]"
    
    - name: Run E2E tests
      run: |
        pytest tests/e2e/ -v \
          --cov=app \
          --cov-report=xml \
          --junitxml=pytest-e2e.xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v4
      with:
        files: ./coverage.xml
    
    - name: Upload test results
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: pytest-e2e-results
        path: pytest-e2e.xml
```

### Pre-commit Hook

```bash
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest-e2e
        name: Run E2E Tests
        entry: pytest tests/e2e/ -v
        language: system
        pass_filenames: false
        always_run: true
```

---

## Performance Benchmarks

Typical test execution times:

| Test Suite | Count | Avg Time |
|------------|-------|----------|
| `TestE2EFullFlow` | 3 | ~2s |
| `TestE2EFailureModes` | 4 | ~3s |
| `TestE2EConcurrency` | 2 | ~2s |
| `TestE2EDatabasePersistence` | 3 | ~1s |
| **Total** | **12** | **~8s** |

---

## Troubleshooting

### Common Issues

#### 1. Test Hangs

**Cause:** Async event stream not completing

**Solution:**
```python
# Ensure events have a clear end
async def mock_listen_events(session_id):
    yield {"event": "complete"}
    # Don't leave hanging coroutines
```

#### 2. Database Lock

**Cause:** SQLite database not properly released

**Solution:**
```python
@pytest_asyncio.fixture
async def db_session():
    await init_db()
    yield
    from app.infrastructure.db.database import engine
    await engine.dispose()  # Critical!
```

#### 3. Mock Not Called

**Cause:** Wrong mock object passed

**Solution:**
```python
# Verify mock is being used
assert mock_git.clone_calls == [(expected_url, expected_path)]
```

#### 4. Timeout Too Short

**Cause:** Test logic takes longer than `IDLE_TIMEOUT`

**Solution:**
```python
@pytest.mark.asyncio
async def test_slow_operation(monkeypatch):
    monkeypatch.setattr(settings, "IDLE_TIMEOUT", 10)  # Increase for this test
    # ... test code
```

---

## Next Steps

1. **Add More Scenarios**: Expand coverage for edge cases
2. **Integration Tests**: Add tests with real GitHub API (sandbox mode)
3. **Load Testing**: Test concurrent task handling under load
4. **Chaos Testing**: Randomly inject failures to test resilience

---

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [Python asyncio testing guide](https://docs.python.org/3/library/asyncio-testing.html)
