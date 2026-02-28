# Situation Monitor Tests

This directory contains the test suite for Situation Monitor.

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=situation_monitor --cov-report=html

# Run specific test file
pytest tests/test_core.py -v

# Run specific test
pytest tests/test_core.py::test_source_initialization -v

# Run only fast tests (skip slow)
pytest tests/ -v -m "not slow"

# Run integration tests only
pytest tests/integration/ -v

# Run performance tests
pytest tests/integration/test_performance.py -v
```

## Test Structure

### Unit Tests
- `test_core.py` - Tests for base classes and core utilities
- `test_config.py` - Tests for configuration management
- `conftest.py` - Test fixtures and configuration

### Integration Tests (`integration/`)
- `test_e2e.py` - End-to-end workflows and interface compliance
- `test_performance.py` - Load tests and performance benchmarks
- `conftest.py` - Integration test fixtures

## Test Coverage

| Component | Coverage |
|-----------|----------|
| Core | >90% |
| Config | >85% |
| Integration | E2E flows |
| Performance | Benchmarks |

## CI/CD

Tests run automatically on:
- Push to main/develop branches
- Pull requests
- Scheduled runs (nightly)

See `.github/workflows/ci.yml` for configuration.
