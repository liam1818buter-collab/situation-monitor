"""
Integration tests for Situation Monitor.

These tests validate:
- End-to-end workflows
- Module interface compliance
- Data flow validation
- Error handling and recovery
- Performance under load

Run with:
    pytest tests/integration/ -v

Run excluding slow tests:
    pytest tests/integration/ -v -m "not slow"

Run only performance tests:
    pytest tests/integration/test_performance.py -v
"""
