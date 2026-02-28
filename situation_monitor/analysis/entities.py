import spacy
from typing import List


class EntityExtractor:
    def __init__(self):
        self.nlp = spacy.load("en_core_web_sm")
    
    def extract(self, text: str) -> List[str]:
        """Extract named entities from text"""
        doc = self.nlp(text[:10000])  # Limit for speed
        return list(set([ent.text for ent in doc.ents if ent.label_ in ['PERSON', 'ORG', 'GPE', 'PRODUCT']]))
