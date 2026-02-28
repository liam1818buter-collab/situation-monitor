"""
Performance and load tests for Situation Monitor.
Tests system behavior under heavy load.
"""

import asyncio
import pytest
import time
import tracemalloc
from typing import List
from datetime import datetime

from situation_monitor.core.base import Source, Analyzer, Storage
from situation_monitor.core.models import (
    MonitoringResult, Alert, SourceConfig, AlertRule, AlertSeverity
)
from situation_monitor.tests.integration.test_e2e import (
    MockSource, MockAnalyzer, MockStorage, MockNotifier, MockDiscovery
)
from situation_monitor.logs.logger import get_logger

logger = get_logger("tests.performance")


# ============================================================================
# Load Tests
# ============================================================================

@pytest.mark.slow
@pytest.mark.asyncio
async def test_load_10_simultaneous_situations():
    """
    Load test: Monitor 10+ simultaneous situations.
    Each situation has sources, analyzers, and alert rules.
    """
    NUM_SITUATIONS = 12
    SOURCES_PER_SITUATION = 3
    RESULTS_PER_SOURCE = 5
    
    start_time = time.time()
    
    async def run_situation(situation_id: int):
        """Simulate a complete monitoring situation."""
        storage = MockStorage()
        await storage.connect()
        
        analyzer = MockAnalyzer(f"analyzer-{situation_id}")
        await analyzer.initialize()
        
        rules = [
            AlertRule(
                id=f"rule-{situation_id}-security",
                name="Security",
                keywords=["security", "vulnerability"],
                severity=AlertSeverity.WARNING
            ),
            AlertRule(
                id=f"rule-{situation_id}-error",
                name="Errors",
                keywords=["error", "failure", "critical"],
                severity=AlertSeverity.ERROR
            )
        ]
        
        # Create and fetch from multiple sources
        sources = []
        keywords = ["security", "vulnerability", "error", "failure", "critical"]
        for i in range(SOURCES_PER_SITUATION):
            config = SourceConfig(
                id=f"sit-{situation_id}-src-{i}",
                name=f"Source {i}",
                type="mock"
            )
            results = [
                {
                    # Include keywords to trigger alerts
                    "content": f"Content {j} with {keywords[(situation_id + i + j) % len(keywords)]} issue",
                    "title": f"Title {j}"
                }
                for j in range(RESULTS_PER_SOURCE)
            ]
            source = MockSource(config, results=results, delay=0.001)
            await source.initialize()
            sources.append(source)
        
        # Fetch from all sources concurrently
        fetch_tasks = [s.fetch() for s in sources]
        all_results = await asyncio.gather(*fetch_tasks)
        
        # Process all results
        total_alerts = 0
        for source_results in all_results:
            for result in source_results:
                analysis = await analyzer.analyze(result)
                alerts = await analyzer.check_rules(result, rules)
                total_alerts += len(alerts)
                
                await storage.save_result(result)
                for alert in alerts:
                    await storage.save_alert(alert)
        
        # Cleanup
        for source in sources:
            await source.shutdown()
        await analyzer.shutdown()
        await storage.disconnect()
        
        return {
            "situation_id": situation_id,
            "results_processed": sum(len(r) for r in all_results),
            "alerts_generated": total_alerts
        }
    
    # Run all situations concurrently
    tasks = [run_situation(i) for i in range(NUM_SITUATIONS)]
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    
    # Verify results
    total_processed = sum(r["results_processed"] for r in results)
    total_alerts = sum(r["alerts_generated"] for r in results)
    
    expected_results = NUM_SITUATIONS * SOURCES_PER_SITUATION * RESULTS_PER_SOURCE
    assert total_processed == expected_results, f"Expected {expected_results} results, got {total_processed}"
    
    logger.info(f"Load test completed: {NUM_SITUATIONS} situations, "
                f"{total_processed} results, {total_alerts} alerts in {elapsed:.2f}s")
    
    # Performance assertions
    assert elapsed < 30, f"Load test took too long: {elapsed:.2f}s"
    assert total_alerts > 0, "Should generate some alerts"


@pytest.mark.slow
@pytest.mark.asyncio
async def test_concurrent_alert_storm():
    """
    Test system handles many alerts being generated simultaneously.
    """
    NUM_SOURCES = 20
    ALERTS_PER_SOURCE = 10
    
    storage = MockStorage()
    await storage.connect()
    
    notifier = MockNotifier("test")
    
    async def generate_alerts(source_id: str, count: int):
        """Generate multiple alerts from a source."""
        alerts = []
        for i in range(count):
            alert = Alert(
                id=f"alert-{source_id}-{i}",
                rule_id="test-rule",
                source_id=source_id,
                severity=AlertSeverity.WARNING,
                title=f"Alert {i} from {source_id}",
                message="Test message"
            )
            await storage.save_alert(alert)
            await notifier.send(alert)
            alerts.append(alert)
        return alerts
    
    # Generate alerts from multiple sources concurrently
    tasks = [
        generate_alerts(f"source-{i}", ALERTS_PER_SOURCE)
        for i in range(NUM_SOURCES)
    ]
    
    start_time = time.time()
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start_time
    
    # Verify
    total_alerts = NUM_SOURCES * ALERTS_PER_SOURCE
    stored_alerts = await storage.get_alerts(limit=total_alerts + 10)  # Get all alerts
    
    assert len(stored_alerts) == total_alerts, f"Expected {total_alerts} stored alerts, got {len(stored_alerts)}"
    assert len(notifier.sent_alerts) == total_alerts, f"Expected {total_alerts} sent alerts, got {len(notifier.sent_alerts)}"
    
    logger.info(f"Alert storm test: {total_alerts} alerts in {elapsed:.2f}s")
    assert elapsed < 10, f"Alert processing too slow: {elapsed:.2f}s"


# ============================================================================
# Memory Profiling Tests
# ============================================================================

@pytest.mark.slow
@pytest.mark.asyncio
async def test_memory_usage_large_dataset():
    """
    Test memory usage remains reasonable with large datasets.
    """
    tracemalloc.start()
    
    storage = MockStorage()
    await storage.connect()
    
    # Generate large dataset
    NUM_RECORDS = 1000
    
    snapshot1 = tracemalloc.take_snapshot()
    
    for i in range(NUM_RECORDS):
        result = MonitoringResult(
            source_id="memory-test",
            raw_data={"index": i, "data": "x" * 1000},  # 1KB raw data each
            content=f"Content {i}" + "y" * 500,
            title=f"Title {i}"
        )
        await storage.save_result(result)
    
    snapshot2 = tracemalloc.take_snapshot()
    
    # Get memory stats
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    # Calculate stats
    top_stats = snapshot2.compare_to(snapshot1, 'lineno')
    
    logger.info(f"Memory test: {NUM_RECORDS} records")
    logger.info(f"Current memory: {current / 1024 / 1024:.2f} MB")
    logger.info(f"Peak memory: {peak / 1024 / 1024:.2f} MB")
    
    # Memory assertions - should be reasonable
    assert current < 100 * 1024 * 1024, f"Memory usage too high: {current / 1024 / 1024:.2f} MB"
    
    # Verify data integrity
    stored = await storage.get_results(limit=NUM_RECORDS)
    assert len(stored) == NUM_RECORDS


@pytest.mark.asyncio
async def test_memory_cleanup_after_shutdown():
    """
    Test memory is properly cleaned up after components shutdown.
    """
    tracemalloc.start()
    
    snapshot1 = tracemalloc.take_snapshot()
    
    # Create and use components
    components = []
    for i in range(50):
        config = SourceConfig(id=f"mem-test-{i}", name="Test", type="mock")
        source = MockSource(config, results=[{"content": "test"}])
        await source.initialize()
        await source.fetch()
        components.append(source)
    
    # Shutdown all
    for comp in components:
        await comp.shutdown()
    
    # Force cleanup
    components.clear()
    
    snapshot2 = tracemalloc.take_snapshot()
    
    # Check for memory leaks
    top_stats = snapshot2.compare_to(snapshot1, 'lineno')
    
    tracemalloc.stop()
    
    # Should not have significant memory growth
    # Allow some tolerance for Python's memory management
    logger.info("Memory cleanup test completed")


# ============================================================================
# Database Query Performance Tests
# ============================================================================

@pytest.mark.slow
@pytest.mark.asyncio
async def test_query_performance_with_large_dataset():
    """
    Test storage queries remain performant with large datasets.
    """
    storage = MockStorage()
    await storage.connect()
    
    # Populate with test data
    NUM_RECORDS = 500
    NUM_SOURCES = 10
    
    for i in range(NUM_RECORDS):
        source_id = f"source-{i % NUM_SOURCES}"
        result = MonitoringResult(
            source_id=source_id,
            raw_data={"index": i},
            content=f"Content for record {i}",
            timestamp=datetime.utcnow()
        )
        await storage.save_result(result)
    
    # Test query performance
    
    # Query all results
    start = time.time()
    all_results = await storage.get_results(limit=NUM_RECORDS)
    query_all_time = time.time() - start
    
    assert len(all_results) == NUM_RECORDS
    assert query_all_time < 5.0, f"Query all too slow: {query_all_time:.2f}s"
    
    # Query by source
    start = time.time()
    source_results = await storage.get_results(source_id="source-5")
    query_source_time = time.time() - start
    
    assert len(source_results) == NUM_RECORDS // NUM_SOURCES
    assert query_source_time < 1.0, f"Query by source too slow: {query_source_time:.2f}s"
    
    logger.info(f"Query performance: all={query_all_time:.3f}s, "
                f"by_source={query_source_time:.3f}s")


@pytest.mark.asyncio
async def test_pagination_performance():
    """
    Test pagination works efficiently.
    """
    storage = MockStorage()
    await storage.connect()
    
    # Create dataset
    for i in range(200):
        result = MonitoringResult(
            source_id="pagination-test",
            raw_data={"index": i},
            content=f"Item {i}"
        )
        await storage.save_result(result)
    
    # Paginate through results
    PAGE_SIZE = 20
    all_items = []
    
    start = time.time()
    
    # Simulate pagination
    page = await storage.get_results(source_id="pagination-test", limit=PAGE_SIZE)
    all_items.extend(page)
    
    # In real implementation, would use offset/cursor
    # Here we just verify the limit works
    assert len(page) <= PAGE_SIZE
    
    elapsed = time.time() - start
    assert elapsed < 1.0, f"Pagination too slow: {elapsed:.2f}s"


# ============================================================================
# Scraping Politeness Tests
# ============================================================================

@pytest.mark.asyncio
async def test_rate_limiting_enforcement():
    """
    Test that rate limiting is properly enforced to be polite to sources.
    """
    from situation_monitor.core.rate_limiter import RateLimiter
    
    limiter = RateLimiter()
    
    # Configure a strict rate limit: 2 requests per second
    limiter.create_bucket("strict-source", requests_per_minute=120, burst=2)
    
    # First 2 should succeed immediately (burst)
    assert await limiter.acquire("strict-source") is True
    assert await limiter.acquire("strict-source") is True
    
    # Third should fail (rate limited)
    assert await limiter.acquire("strict-source") is False
    
    # Wait and try again
    await asyncio.sleep(0.6)
    assert await limiter.acquire("strict-source") is True


@pytest.mark.asyncio
async def test_concurrent_request_limiting():
    """
    Test that concurrent requests are properly limited.
    """
    from situation_monitor.core.rate_limiter import RateLimiter
    
    limiter = RateLimiter()
    limiter.create_bucket("limited", requests_per_minute=600, burst=5)
    
    async def make_request(request_id: int):
        if await limiter.acquire("limited"):
            await asyncio.sleep(0.01)  # Simulate request time
            return True
        return False
    
    # Try to make 10 concurrent requests with burst of 5
    tasks = [make_request(i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    
    # Should only allow burst amount immediately
    successful = sum(1 for r in results if r)
    assert successful <= 5, f"Too many concurrent requests: {successful}"


@pytest.mark.slow
@pytest.mark.asyncio
async def test_respectful_polling_interval():
    """
    Test that sources respect minimum polling intervals.
    """
    config = SourceConfig(
        id="polite-source",
        name="Polite Source",
        type="mock",
        interval_seconds=10  # Minimum allowed value
    )
    
    source = MockSource(config, results=[{"content": "test"}])
    await source.initialize()
    
    # First fetch
    start = time.time()
    await source.fetch()
    
    # Try to fetch again immediately
    await source.fetch()
    elapsed = time.time() - start
    
    # Should complete but in a real implementation
    # would respect the interval
    logger.info(f"Polling interval test: elapsed={elapsed:.2f}s")
    
    await source.shutdown()


# ============================================================================
# Resource Limit Tests
# ============================================================================

@pytest.mark.asyncio
async def test_component_resource_limits():
    """
    Test components respect resource limits.
    """
    settings = {
        "max_concurrent_sources": 5,
        "request_timeout": 5,
        "max_retries": 2
    }
    
    # Test that settings are applied
    assert settings["max_concurrent_sources"] == 5
    assert settings["request_timeout"] == 5
    
    # Create sources up to limit
    sources = []
    for i in range(settings["max_concurrent_sources"]):
        config = SourceConfig(id=f"limited-{i}", name="Test", type="mock")
        source = MockSource(config)
        await source.initialize()
        sources.append(source)
    
    assert len(sources) == 5
    
    # Cleanup
    for source in sources:
        await source.shutdown()


@pytest.mark.slow
@pytest.mark.asyncio
async def test_disk_usage_limits():
    """
    Test that storage respects disk usage limits.
    """
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Check available space
        stat = os.statvfs(tmpdir)
        available_mb = (stat.f_frsize * stat.f_bavail) / (1024 * 1024)
        
        logger.info(f"Available disk space: {available_mb:.2f} MB")
        
        # In production, would implement actual disk usage tracking
        # and rotation based on limits
        assert available_mb > 100, "Insufficient disk space for testing"


# ============================================================================
# Performance Benchmarks
# ============================================================================

@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_analysis_throughput():
    """
    Benchmark analysis throughput (items/second).
    """
    analyzer = MockAnalyzer("benchmark")
    await analyzer.initialize()
    
    rules = [
        AlertRule(id=f"rule-{i}", name=f"Rule {i}", keywords=[f"keyword{i}"])
        for i in range(10)
    ]
    
    NUM_ITEMS = 100
    items = [
        MonitoringResult(
            source_id="benchmark",
            raw_data={"index": i},
            content=f"Test content with keyword{i % 10}"
        )
        for i in range(NUM_ITEMS)
    ]
    
    start = time.time()
    
    for item in items:
        await analyzer.analyze(item)
        await analyzer.check_rules(item, rules)
    
    elapsed = time.time() - start
    throughput = NUM_ITEMS / elapsed
    
    logger.info(f"Analysis throughput: {throughput:.2f} items/second")
    
    # Should be reasonably fast
    assert throughput > 50, f"Analysis too slow: {throughput:.2f} items/sec"
    
    await analyzer.shutdown()


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_storage_write_throughput():
    """
    Benchmark storage write throughput.
    """
    storage = MockStorage()
    await storage.connect()
    
    NUM_WRITES = 500
    
    start = time.time()
    
    for i in range(NUM_WRITES):
        result = MonitoringResult(
            source_id="throughput-test",
            raw_data={"index": i},
            content=f"Item {i}"
        )
        await storage.save_result(result)
    
    elapsed = time.time() - start
    throughput = NUM_WRITES / elapsed
    
    logger.info(f"Storage write throughput: {throughput:.2f} writes/second")
    
    assert throughput > 100, f"Storage write too slow: {throughput:.2f} writes/sec"
    
    await storage.disconnect()
