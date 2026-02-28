# Situation Monitor Integration Tests

This directory contains comprehensive integration tests for the Situation Monitor system.

## Test Structure

```
tests/integration/
├── __init__.py           # Package initialization
├── conftest.py           # Test fixtures and configuration
├── test_e2e.py          # End-to-end and interface tests
└── test_performance.py   # Performance and load tests
```

## Running Tests

### Run all integration tests (excluding slow ones)
```bash
pytest tests/integration/ -v -m "not slow"
```

### Run all tests including slow ones
```bash
pytest tests/integration/ -v
```

### Run specific test file
```bash
pytest tests/integration/test_e2e.py -v
pytest tests/integration/test_performance.py -v
```

### Run with coverage
```bash
pytest tests/integration/ --cov=situation_monitor --cov-report=html
```

### Run performance benchmarks only
```bash
pytest tests/integration/test_performance.py -v -m "benchmark"
```

## Test Categories

### End-to-End Tests (`test_e2e.py`)

- **test_e2e_full_flow**: Complete workflow from situation creation to alert
- **test_*_interface_compliance**: Module interface validation
- **test_data_flow_***: Data flow validation
- **test_*_handling**: Error injection and recovery tests

### Performance Tests (`test_performance.py`)

- **test_load_10_simultaneous_situations**: Load testing with 12 concurrent situations
- **test_memory_usage_***: Memory profiling and leak detection
- **test_*_throughput**: Performance benchmarks
- **test_rate_limiting_***: Scraping politeness verification

## Test Markers

- `@pytest.mark.slow`: Tests that take longer to run (excluded by default)
- `@pytest.mark.integration`: Integration tests
- `@pytest.mark.benchmark`: Performance benchmarks

## Fixtures

Common fixtures available in `conftest.py`:

- `temp_dir`: Temporary directory for test files
- `mock_settings`: Pre-configured test settings
- `clean_storage`: Fresh storage instance
- `sample_source_config`: Example source configuration
- `sample_alert_rules`: Example alert rules
- `sample_monitoring_results`: Example monitoring results
- `sample_alerts`: Example alerts
- `sample_parsed_situation`: Example parsed situation

## CI/CD Integration

Tests are automatically run in GitHub Actions:
- Linting (Black, Ruff, MyPy)
- Unit tests (Python 3.10, 3.11, 3.12)
- Integration tests
- Performance tests (on main branch)
- Security scanning

See `.github/workflows/ci.yml` for details.
