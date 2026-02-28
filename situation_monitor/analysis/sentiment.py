from transformers import pipeline
from typing import List
from ..core.base import Document, AnalysisResult


class SentimentAnalyzer:
    def __init__(self):
        # Use lightweight model
        self.classifier = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
    
    def analyze(self, text: str) -> float:
        """Returns sentiment score from -1 (negative) to 1 (positive)"""
        result = self.classifier(text[:512])  # Truncate for speed
        label = result[0]['label']
        score = result[0]['score']
        return score if label == 'POSITIVE' else -score
