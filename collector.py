"""
CollectorEngine for fetching and extracting content from sources.

Uses scrapling for robust web scraping with anti-bot protection.
Includes deduplication, change detection, and content extraction.
"""

import asyncio
import hashlib
import re
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable, Set
from urllib.parse import urljoin, urlparse
import logging

# Import models
from models import RawDocument, ProcessedDocument, ExtractedContent, DocumentStatus, DeadLetterItem
from interfaces import Source, SourceConfig, RateLimit

# Scrapling imports - add venv path for access
import sys
sys.path.insert(0, '/root/clawd/venv/lib/python3.12/site-packages')

try:
    from scrapling.fetchers import StealthyFetcher, Fetcher
    from scrapling.defaults import Fetcher as DefaultFetcher
    SCRAPLING_AVAILABLE = True
except ImportError:
    SCRAPLING_AVAILABLE = False
    logging.warning("Scrapling not available, falling back to basic fetcher")


logger = logging.getLogger(__name__)


class ContentExtractor:
    """Extract structured content from HTML."""
    
    # Common CSS selectors for article content
    DEFAULT_SELECTORS = {
        'title': [
            'h1', 'article h1', '.article-title', '.entry-title',
            '[class*="title"]', 'meta[property="og:title"]'
        ],
        'author': [
            '[class*="author"]', '[class*="byline"]', '.byline',
            'meta[name="author"]', '[rel="author"]'
        ],
        'date': [
            'time', '[class*="date"]', '[class*="published"]',
            'meta[property="article:published_time"]',
            'meta[name="publish-date"]'
        ],
        'article': [
            'article', '[class*="article-content"]', '[class*="entry-content"]',
            '[class*="post-content"]', '.content', 'main',
            '[role="main"]'
        ],
    }
    
    def __init__(self, custom_selectors: Optional[Dict[str, List[str]]] = None):
        self.selectors = custom_selectors or self.DEFAULT_SELECTORS
    
    def extract(self, html: str, url: str, custom_selectors: Optional[Dict[str, str]] = None) -> ExtractedContent:
        """
        Extract structured content from HTML.
        
        Args:
            html: Raw HTML content
            url: Source URL for context
            custom_selectors: Optional source-specific selectors
            
        Returns:
            ExtractedContent with title, author, date, text
        """
        if not SCRAPLING_AVAILABLE:
            return self._basic_extract(html, url)
        
        try:
            from scrapling.parser import TextHandler
            parser = TextHandler(html, url=url)
            
            # Extract title
            title = self._extract_title(parser, custom_selectors)
            
            # Extract author
            author = self._extract_author(parser, custom_selectors)
            
            # Extract date
            publish_date = self._extract_date(parser, custom_selectors)
            
            # Extract article text
            article_text = self._extract_article_text(parser, custom_selectors)
            
            # Extract links
            links = self._extract_links(parser, url)
            
            # Extract images
            images = self._extract_images(parser, url)
            
            return ExtractedContent(
                title=title or "Untitled",
                author=author,
                publish_date=publish_date,
                article_text=article_text,
                links=links,
                images=images,
            )
            
        except Exception as e:
            logger.error(f"Extraction error for {url}: {e}")
            return self._basic_extract(html, url)
    
    def _extract_title(self, parser, custom_selectors: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Extract article title."""
        # Try meta tags first
        og_title = parser.css_first('meta[property="og:title"]')
        if og_title:
            return og_title.attributes.get('content')
        
        twitter_title = parser.css_first('meta[name="twitter:title"]')
        if twitter_title:
            return twitter_title.attributes.get('content')
        
        # Try title tag
        title_tag = parser.css_first('title')
        if title_tag:
            return title_tag.text(strip=True)
        
        # Try heading selectors
        selectors = custom_selectors.get('title', []) if custom_selectors else []
        selectors.extend(self.selectors['title'])
        
        for selector in selectors:
            elem = parser.css_first(selector)
            if elem:
                return elem.text(strip=True)
        
        return None
    
    def _extract_author(self, parser, custom_selectors: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Extract article author."""
        # Try meta tags
        meta_author = parser.css_first('meta[name="author"]')
        if meta_author:
            return meta_author.attributes.get('content')
        
        # Try selectors
        selectors = custom_selectors.get('author', []) if custom_selectors else []
        selectors.extend(self.selectors['author'])
        
        for selector in selectors:
            elem = parser.css_first(selector)
            if elem:
                return elem.text(strip=True)
        
        return None
    
    def _extract_date(self, parser, custom_selectors: Optional[Dict[str, str]] = None) -> Optional[datetime]:
        """Extract publish date."""
        # Try meta tags
        meta_date = parser.css_first('meta[property="article:published_time"]')
        if meta_date:
            date_str = meta_date.attributes.get('content')
            if date_str:
                return self._parse_date(date_str)
        
        # Try time elements
        time_elem = parser.css_first('time')
        if time_elem:
            datetime_attr = time_elem.attributes.get('datetime')
            if datetime_attr:
                return self._parse_date(datetime_attr)
            return self._parse_date(time_elem.text(strip=True))
        
        return None
    
    def _extract_article_text(self, parser, custom_selectors: Optional[Dict[str, str]] = None) -> str:
        """Extract main article text."""
        # Try article selectors
        selectors = custom_selectors.get('article', []) if custom_selectors else []
        selectors.extend(self.selectors['article'])
        
        for selector in selectors:
            elem = parser.css_first(selector)
            if elem:
                # Get text, filtering out script/style
                text = elem.text(separator='\n', strip=True)
                return self._clean_text(text)
        
        # Fallback: get all paragraphs
        paragraphs = parser.css('p')
        texts = [p.text(strip=True) for p in paragraphs if len(p.text(strip=True)) > 50]
        return self._clean_text('\n\n'.join(texts))
    
    def _extract_links(self, parser, base_url: str) -> List[str]:
        """Extract all links from the page."""
        links = []
        for anchor in parser.css('a[href]'):
            href = anchor.attributes.get('href')
            if href:
                absolute = urljoin(base_url, href)
                links.append(absolute)
        return list(set(links))
    
    def _extract_images(self, parser, base_url: str) -> List[str]:
        """Extract image URLs."""
        images = []
        for img in parser.css('img[src]'):
            src = img.attributes.get('src')
            if src:
                absolute = urljoin(base_url, src)
                images.append(absolute)
        return list(set(images))
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime."""
        from dateutil import parser as date_parser
        try:
            return date_parser.parse(date_str)
        except:
            return None
    
    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        # Remove extra whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()
    
    def _basic_extract(self, html: str, url: str) -> ExtractedContent:
        """Fallback extraction using basic regex."""
        # Extract title
        title_match = re.search(r'<title>(.*?)</title>', html, re.I | re.S)
        title = title_match.group(1).strip() if title_match else "Untitled"
        
        # Extract text (very basic)
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return ExtractedContent(
            title=title,
            article_text=text[:5000],  # Limit for basic extraction
        )


class DeduplicationStore:
    """Store for content deduplication using content hashes."""
    
    def __init__(self, max_size: int = 10000):
        self._hashes: Set[str] = set()
        self._url_hashes: Dict[str, str] = {}  # URL -> content hash
        self._max_size = max_size
    
    def is_duplicate(self, content_hash: str) -> bool:
        """Check if content hash is already known."""
        return content_hash in self._hashes
    
    def is_url_changed(self, url: str, content_hash: str) -> bool:
        """Check if URL content has changed."""
        if url not in self._url_hashes:
            return True
        return self._url_hashes[url] != content_hash
    
    def add(self, content_hash: str, url: Optional[str] = None):
        """Add content hash to store."""
        self._hashes.add(content_hash)
        if url:
            self._url_hashes[url] = content_hash
        
        # Simple LRU: if too big, clear oldest half
        if len(self._hashes) > self._max_size:
            self._hashes = set(list(self._hashes)[self._max_size//2:])
    
    def clear(self):
        """Clear all stored hashes."""
        self._hashes.clear()
        self._url_hashes.clear()


class CircuitBreaker:
    """Circuit breaker pattern for failing sources."""
    
    STATE_CLOSED = "closed"      # Normal operation
    STATE_OPEN = "open"          # Failing, reject requests
    STATE_HALF_OPEN = "half_open"  # Testing if recovered
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self._state = self.STATE_CLOSED
        self._failures = 0
        self._last_failure_time: Optional[datetime] = None
        self._half_open_calls = 0
    
    @property
    def state(self) -> str:
        if self._state == self.STATE_OPEN:
            # Check if we should try half-open
            if self._last_failure_time:
                elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self._state = self.STATE_HALF_OPEN
                    self._half_open_calls = 0
        return self._state
    
    def can_execute(self) -> bool:
        state = self.state
        if state == self.STATE_CLOSED:
            return True
        elif state == self.STATE_OPEN:
            return False
        elif state == self.STATE_HALF_OPEN:
            return self._half_open_calls < self.half_open_max_calls
        return False
    
    def record_success(self):
        """Record successful execution."""
        self._failures = 0
        if self._state == self.STATE_HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                self._state = self.STATE_CLOSED
                self._half_open_calls = 0
    
    def record_failure(self):
        """Record failed execution."""
        self._failures += 1
        self._last_failure_time = datetime.utcnow()
        
        if self._state == self.STATE_HALF_OPEN:
            self._state = self.STATE_OPEN
            self._half_open_calls = 0
        elif self._failures >= self.failure_threshold:
            self._state = self.STATE_OPEN


class CollectorEngine:
    """
    Engine for collecting content from sources.
    
    Features:
    - Async fetching via scrapling
    - Content extraction and cleaning
    - Deduplication across sources
    - Change detection
    - Circuit breaker pattern for resilience
    """
    
    def __init__(
        self,
        use_stealth: bool = True,
        request_timeout: float = 30.0,
        max_concurrent: int = 5,
    ):
        self.use_stealth = use_stealth and SCRAPLING_AVAILABLE
        self.request_timeout = request_timeout
        self.max_concurrent = max_concurrent
        
        # Components
        self.extractor = ContentExtractor()
        self.dedup_store = DeduplicationStore()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.dead_letter_queue: List[DeadLetterItem] = []
        
        # Rate limiting per domain
        self._last_request_time: Dict[str, datetime] = {}
        self._domain_semaphores: Dict[str, asyncio.Semaphore] = {}
        
        # Processing queue
        self._processing_queue: asyncio.Queue = asyncio.Queue()
        self._processed_callback: Optional[Callable] = None
        
        # Statistics
        self.stats = {
            'fetched': 0,
            'deduplicated': 0,
            'failed': 0,
            'dead_letter': 0,
        }
    
    def _get_fetcher(self):
        """Get appropriate fetcher based on configuration."""
        if not SCRAPLING_AVAILABLE:
            return None
        
        if self.use_stealth:
            fetcher = StealthyFetcher()
            fetcher.adaptive = True
            return fetcher
        else:
            return Fetcher()
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc.lower()
    
    def _get_circuit_breaker(self, source_id: str) -> CircuitBreaker:
        """Get or create circuit breaker for source."""
        if source_id not in self.circuit_breakers:
            self.circuit_breakers[source_id] = CircuitBreaker()
        return self.circuit_breakers[source_id]
    
    async def _rate_limited_fetch(self, url: str, headers: Optional[Dict] = None) -> RawDocument:
        """Fetch URL with per-domain rate limiting."""
        domain = self._get_domain(url)
        
        # Get or create semaphore for domain
        if domain not in self._domain_semaphores:
            self._domain_semaphores[domain] = asyncio.Semaphore(self.max_concurrent)
        
        async with self._domain_semaphores[domain]:
            # Check rate limit
            await self._enforce_rate_limit(domain)
            
            try:
                fetcher = self._get_fetcher()
                
                if fetcher:
                    # Use scrapling
                    page = await asyncio.wait_for(
                        asyncio.to_thread(fetcher.fetch, url, headless=True),
                        timeout=self.request_timeout
                    )
                    
                    raw_doc = RawDocument(
                        source_id=domain,
                        url=url,
                        raw_html=page.content,
                        raw_text=page.text,
                        headers=getattr(page, 'headers', {}),
                        status_code=200,
                    )
                else:
                    # Fallback to basic fetch
                    raw_doc = await self._basic_fetch(url, headers)
                
                self._last_request_time[domain] = datetime.utcnow()
                return raw_doc
                
            except asyncio.TimeoutError:
                raise Exception(f"Request timeout for {url}")
            except Exception as e:
                raise Exception(f"Fetch failed for {url}: {e}")
    
    async def _basic_fetch(self, url: str, headers: Optional[Dict] = None) -> RawDocument:
        """Basic fetch using httpx as fallback."""
        import httpx
        
        async with httpx.AsyncClient(timeout=self.request_timeout) as client:
            response = await client.get(url, headers=headers or {})
            response.raise_for_status()
            
            return RawDocument(
                source_id=self._get_domain(url),
                url=url,
                raw_html=response.text,
                headers=dict(response.headers),
                status_code=response.status_code,
            )
    
    async def _enforce_rate_limit(self, domain: str):
        """Enforce rate limit for domain."""
        default_rate = RateLimit()  # 10 req/min default
        min_interval = default_rate.min_interval_seconds
        
        if domain in self._last_request_time:
            elapsed = (datetime.utcnow() - self._last_request_time[domain]).total_seconds()
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
    
    async def fetch_url(self, url: str, source_id: str, headers: Optional[Dict] = None) -> Optional[RawDocument]:
        """
        Fetch a single URL with full pipeline.
        
        Args:
            url: URL to fetch
            source_id: Identifier for the source
            headers: Optional custom headers
            
        Returns:
            RawDocument or None if deduplicated/failed
        """
        circuit_breaker = self._get_circuit_breaker(source_id)
        
        if not circuit_breaker.can_execute():
            logger.warning(f"Circuit breaker open for {source_id}")
            return None
        
        try:
            raw_doc = await self._rate_limited_fetch(url, headers)
            raw_doc.source_id = source_id
            
            # Deduplication check
            if self.dedup_store.is_duplicate(raw_doc.content_hash):
                logger.debug(f"Duplicate content: {url}")
                raw_doc.status = DocumentStatus.DUPLICATE
                self.stats['deduplicated'] += 1
                return None
            
            # Change detection (if URL seen before)
            if not self.dedup_store.is_url_changed(url, raw_doc.content_hash):
                logger.debug(f"No change detected: {url}")
                return None
            
            # Mark as seen
            self.dedup_store.add(raw_doc.content_hash, url)
            
            # Record success
            circuit_breaker.record_success()
            raw_doc.status = DocumentStatus.EXTRACTED
            raw_doc.record_success()
            
            self.stats['fetched'] += 1
            return raw_doc
            
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            circuit_breaker.record_failure()
            self.stats['failed'] += 1
            
            # Add to dead letter queue
            self._add_to_dead_letter(source_id, url, str(e), type(e).__name__)
            return None
    
    async def fetch_from_source(self, source: Source) -> List[RawDocument]:
        """
        Fetch all content from a source.
        
        Args:
            source: Source instance to fetch from
            
        Returns:
            List of RawDocument objects
        """
        try:
            documents = await source.fetch()
            
            # Process each document
            results = []
            for doc in documents:
                processed = await self.process_document(doc)
                if processed:
                    results.append(processed)
            
            return results
            
        except Exception as e:
            logger.error(f"Source {source.source_id} fetch failed: {e}")
            self._get_circuit_breaker(source.source_id).record_failure()
            return []
    
    async def process_document(self, raw_doc: RawDocument) -> Optional[RawDocument]:
        """
        Process a raw document through deduplication pipeline.
        
        Args:
            raw_doc: Raw document to process
            
        Returns:
            RawDocument if should be stored, None if duplicate
        """
        # Check for duplicate
        if self.dedup_store.is_duplicate(raw_doc.content_hash):
            raw_doc.status = DocumentStatus.DUPLICATE
            self.stats['deduplicated'] += 1
            return None
        
        # Check for changes
        if not self.dedup_store.is_url_changed(raw_doc.url, raw_doc.content_hash):
            return None
        
        # Mark as seen
        self.dedup_store.add(raw_doc.content_hash, raw_doc.url)
        
        return raw_doc
    
    def extract_content(self, raw_doc: RawDocument, custom_selectors: Optional[Dict] = None) -> ProcessedDocument:
        """
        Extract structured content from raw document.
        
        Args:
            raw_doc: Raw document with HTML
            custom_selectors: Optional source-specific CSS selectors
            
        Returns:
            ProcessedDocument with extracted content
        """
        extracted = self.extractor.extract(raw_doc.raw_html, raw_doc.url, custom_selectors)
        
        return ProcessedDocument(
            raw_document_id=raw_doc.id,
            extracted=extracted,
        )
    
    def _add_to_dead_letter(self, source_id: str, url: str, error: str, error_type: str):
        """Add failed item to dead letter queue."""
        item = DeadLetterItem(
            document_id=f"{source_id}:{hashlib.sha256(url.encode()).hexdigest()[:8]}",
            source_id=source_id,
            url=url,
            error_message=error,
            error_type=error_type,
        )
        self.dead_letter_queue.append(item)
        self.stats['dead_letter'] += 1
        
        # Limit queue size
        if len(self.dead_letter_queue) > 1000:
            self.dead_letter_queue = self.dead_letter_queue[-500:]
    
    def get_dead_letter_queue(self) -> List[DeadLetterItem]:
        """Get items in dead letter queue."""
        return self.dead_letter_queue.copy()
    
    def clear_dead_letter(self):
        """Clear dead letter queue."""
        self.dead_letter_queue.clear()
    
    def get_circuit_breaker_states(self) -> Dict[str, str]:
        """Get current state of all circuit breakers."""
        return {sid: cb.state for sid, cb in self.circuit_breakers.items()}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset collection statistics."""
        self.stats = {
            'fetched': 0,
            'deduplicated': 0,
            'failed': 0,
            'dead_letter': 0,
        }
