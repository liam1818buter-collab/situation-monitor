from keybert import KeyBERT
from typing import List


class KeywordExtractor:
    def __init__(self):
        self.kw_model = KeyBERT()
    
    def extract(self, text: str, top_n: int = 10) -> List[str]:
        """Extract top_n keywords from text"""
        if len(text) < 50:
            return []
        keywords = self.kw_model.extract_keywords(text[:5000], keyphrase_ngram_range=(1, 2), stop_words='english', top_n=top_n)
        return [kw[0] for kw in keywords]
