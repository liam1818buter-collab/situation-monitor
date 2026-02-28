from typing import List
from ..core.base import Document, AnalysisResult, Analyzer
from .sentiment import SentimentAnalyzer
from .summarizer import Summarizer
from .entities import EntityExtractor
from .keywords import KeywordExtractor


class AnalysisPipeline(Analyzer):
    def __init__(self):
        self.sentiment = SentimentAnalyzer()
        self.summarizer = Summarizer()
        self.entities = EntityExtractor()
        self.keywords = KeywordExtractor()
    
    async def analyze(self, documents: List[Document]) -> List[AnalysisResult]:
        """Analyze a batch of documents"""
        results = []
        for doc in documents:
            result = AnalysisResult(
                document_id=doc.id,
                sentiment=self.sentiment.analyze(doc.content),
                summary=self.summarizer.summarize(doc.content),
                entities=self.entities.extract(doc.content),
                keywords=self.keywords.extract(doc.content)
            )
            results.append(result)
        return results
