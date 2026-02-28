"""
Example usage of the Situation Monitor Data Collection Scheduler.

This demonstrates how to:
1. Create and configure sources
2. Set up the scheduler
3. Process collected documents
4. Monitor health status
"""

import asyncio
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import modules
from models import RawDocument, ProcessedDocument, SourceType
from interfaces import Source, SourceConfig, WebSource, RateLimit, SourcePriority
from collector import CollectorEngine
from scheduler import CollectionScheduler


class ExampleNewsSource(WebSource):
    """
    Example news source implementation.
    
    In production, this would fetch from actual news APIs or RSS feeds.
    """
    
    def __init__(self, config: SourceConfig):
        super().__init__(config)
        self._demo_urls = [
            "https://example.com/news/article-1",
            "https://example.com/news/article-2",
            "https://example.com/news/article-3",
        ]
    
    async def fetch(self, query=None):
        """Simulate fetching documents."""
        documents = []
        
        for url in self._demo_urls:
            # In production, this would actually fetch the URL
            doc = RawDocument(
                source_id=self.source_id,
                url=url,
                raw_html=f"""
                <html>
                    <head><title>News Article from {url}</title></head>
                    <body>
                        <article>
                            <h1>Breaking News</h1>
                            <p class="byline">By Reporter Name</p>
                            <time datetime="{datetime.utcnow().isoformat()}">
                                {datetime.utcnow().strftime('%Y-%m-%d')}
                            </time>
                            <p>This is example content for {url}.</p>
                            <p>More content here...</p>
                        </article>
                    </body>
                </html>
                """,
            )
            documents.append(doc)
        
        return documents
    
    async def check_updates(self):
        """Check for new/updated content."""
        return await self.fetch()


class ExampleAcademicSource(WebSource):
    """Example academic/journal source."""
    
    def __init__(self, config: SourceConfig):
        super().__init__(config)
        self._demo_urls = [
            "https://arxiv.org/abs/2401.00001",
            "https://arxiv.org/abs/2401.00002",
        ]
    
    async def fetch(self, query=None):
        """Simulate fetching academic papers."""
        documents = []
        
        for url in self._demo_urls:
            doc = RawDocument(
                source_id=self.source_id,
                url=url,
                raw_html=f"""
                <html>
                    <head><title>Research Paper: AI Advances</title></head>
                    <body>
                        <article>
                            <h1>Breakthrough in Multimodal AI</h1>
                            <p class="authors">Dr. Smith, Dr. Johnson</p>
                            <div class="abstract">
                                <p>We present a novel approach to multimodal learning...</p>
                            </div>
                        </article>
                    </body>
                </html>
                """,
            )
            documents.append(doc)
        
        return documents
    
    async def check_updates(self):
        """Check for new papers."""
        return await self.fetch()


async def on_new_document(doc: ProcessedDocument):
    """Callback for new documents."""
    logger.info(f"New document received:")
    logger.info(f"  Title: {doc.extracted.title}")
    logger.info(f"  Author: {doc.extracted.author}")
    logger.info(f"  Word count: {len(doc.extracted.article_text.split())}")


async def on_error(source_id: str, error: Exception):
    """Callback for errors."""
    logger.error(f"Error from {source_id}: {error}")


async def main():
    """Main example."""
    logger.info("Starting Situation Monitor Example")
    
    # Create scheduler
    scheduler = CollectionScheduler(
        db_path="sqlite:///example_monitor.db",
        max_concurrent_jobs=5,
    )
    
    # Add callbacks
    scheduler.add_document_callback(on_new_document)
    scheduler.add_error_callback(on_error)
    
    # Create high-priority news source (checked every 5 minutes)
    news_config = SourceConfig(
        source_id="breaking_news",
        name="Breaking News Aggregator",
        base_url="https://example.com/news",
        source_type="news",
        priority=SourcePriority.CRITICAL,
        rate_limit=RateLimit(requests_per_minute=30),
        check_interval_minutes=5,
    )
    news_source = ExampleNewsSource(news_config)
    
    # Create lower-priority academic source (checked every 6 hours)
    academic_config = SourceConfig(
        source_id="arxiv_papers",
        name="arXiv AI Papers",
        base_url="https://arxiv.org",
        source_type="academic",
        priority=SourcePriority.LOW,
        rate_limit=RateLimit(requests_per_minute=10),
        check_interval_minutes=360,  # 6 hours
    )
    academic_source = ExampleAcademicSource(academic_config)
    
    # Add sources to scheduler
    scheduler.add_source(news_source)
    scheduler.add_source(academic_source)
    
    logger.info(f"Added {len(scheduler._sources)} sources")
    logger.info(f"News check interval: {scheduler._get_check_interval(news_source)} minutes")
    logger.info(f"Academic check interval: {scheduler._get_check_interval(academic_source)} minutes")
    
    # Manually trigger checks for demo
    logger.info("\n--- Manual Check Demo ---")
    await scheduler._execute_source_check("breaking_news")
    
    # Get health status
    health = scheduler.get_health_status()
    logger.info(f"\n--- Health Status ---")
    logger.info(f"Status: {health.status}")
    logger.info(f"Active sources: {health.active_jobs}")
    logger.info(f"Documents in queue: {health.queue_size}")
    logger.info(f"Circuit breakers: {health.circuit_breakers}")
    
    # Get statistics
    stats = scheduler.get_stats()
    logger.info(f"\n--- Statistics ---")
    logger.info(f"Documents collected: {stats['documents_collected']}")
    logger.info(f"Documents queued: {stats['documents_queued']}")
    
    # Demonstrate priority queue behavior
    logger.info(f"\n--- Priority Queue ---")
    for ps in sorted(scheduler._priority_queue):
        logger.info(f"  {ps.source.name}: priority={ps.priority}, next_check={ps.next_check}")
    
    # Demonstrate deduplication
    logger.info(f"\n--- Deduplication Demo ---")
    
    # Create two documents with same content
    doc1 = RawDocument(
        source_id="test",
        url="https://example.com/doc1",
        raw_html="<html><body>Same content</body></html>",
    )
    doc2 = RawDocument(
        source_id="test",
        url="https://example.com/doc2",
        raw_html="<html><body>Same content</body></html>",
    )
    
    result1 = await scheduler.collector.process_document(doc1)
    result2 = await scheduler.collector.process_document(doc2)
    
    logger.info(f"First document: {'kept' if result1 else 'dropped'}")
    logger.info(f"Duplicate document: {'kept' if result2 else 'dropped'}")
    logger.info(f"Dedup store size: {len(scheduler.collector.dedup_store._hashes)}")
    
    logger.info("\nExample completed!")


if __name__ == "__main__":
    asyncio.run(main())
