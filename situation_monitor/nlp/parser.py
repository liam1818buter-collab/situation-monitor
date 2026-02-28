"""
NLP Parser - Situation parsing and entity extraction
Agent 2 Deliverable
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import re
import spacy
from transformers import pipeline


class IntentType(Enum):
    MONITOR = "monitor"
    ALERT = "alert"
    SUMMARIZE = "summarize"
    COMPARE = "compare"


class EventType(Enum):
    CONFLICT = "conflict"
    LEGISLATION = "legislation"
    BREAKTHROUGH = "breakthrough"
    DISRUPTION = "disruption"
    MERGER = "merger"
    ACQUISITION = "acquisition"
    LAUNCH = "launch"
    CRISIS = "crisis"
    RECOVERY = "recovery"
    TREND = "trend"


@dataclass
class ExtractedEntity:
    text: str
    label: str
    start: int
    end: int
    confidence: float = 1.0


@dataclass
class ParsedSituation:
    raw_input: str
    intent: IntentType
    entities: List[ExtractedEntity] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    event_types: List[EventType] = field(default_factory=list)
    geography: List[str] = field(default_factory=list)
    timeframe: str = "ongoing"
    confidence: float = 0.0


class SituationParser:
    """Parse natural language situations into structured queries"""
    
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            # Fallback to basic processing if model not available
            self.nlp = None
        
        self.intent_classifier = None  # Lazy load
        
        # Intent keywords
        self.intent_keywords = {
            IntentType.MONITOR: ["monitor", "track", "watch", "follow", "keep an eye on"],
            IntentType.ALERT: ["alert", "notify", "warn", "inform me", "let me know"],
            IntentType.SUMMARIZE: ["summarize", "digest", "overview", "brief", "report"],
            IntentType.COMPARE: ["compare", "versus", "vs", "difference", "trend"]
        }
        
        # Event type patterns
        self.event_patterns = {
            EventType.CONFLICT: ["tension", "conflict", "war", "dispute", "sanction"],
            EventType.LEGISLATION: ["law", "regulation", "policy", "bill", "act", "legal"],
            EventType.BREAKTHROUGH: ["breakthrough", "discovery", "innovation", "advance"],
            EventType.DISRUPTION: ["disruption", "shortage", "crisis", "problem"],
        }
    
    def parse(self, text: str) -> ParsedSituation:
        """Parse a situation description"""
        # Determine intent
        intent = self._classify_intent(text)
        
        # Extract entities
        entities = self._extract_entities(text)
        
        # Extract keywords
        keywords = self._extract_keywords(text)
        
        # Detect event types
        event_types = self._detect_event_types(text)
        
        # Extract geography
        geography = self._extract_geography(entities)
        
        # Determine timeframe
        timeframe = self._extract_timeframe(text)
        
        return ParsedSituation(
            raw_input=text,
            intent=intent,
            entities=entities,
            keywords=keywords,
            event_types=event_types,
            geography=geography,
            timeframe=timeframe,
            confidence=0.8
        )
    
    def _classify_intent(self, text: str) -> IntentType:
        """Classify the intent of the situation"""
        text_lower = text.lower()
        
        for intent, keywords in self.intent_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return intent
        
        return IntentType.MONITOR  # Default
    
    def _extract_entities(self, text: str) -> List[ExtractedEntity]:
        """Extract named entities"""
        entities = []
        
        if self.nlp:
            doc = self.nlp(text)
            for ent in doc.ents:
                entities.append(ExtractedEntity(
                    text=ent.text,
                    label=ent.label_,
                    start=ent.start_char,
                    end=ent.end_char
                ))
        else:
            # Basic fallback
            # Extract capitalized phrases
            for match in re.finditer(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text):
                entities.append(ExtractedEntity(
                    text=match.group(),
                    label="ENTITY",
                    start=match.start(),
                    end=match.end()
                ))
        
        return entities
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract key terms"""
        # Simple keyword extraction
        words = re.findall(r'\b[A-Za-z]{4,}\b', text.lower())
        # Filter common stop words
        stop_words = {'this', 'that', 'with', 'from', 'they', 'have', 'been', 'their', 'than', 'what'}
        keywords = [w for w in words if w not in stop_words]
        return list(set(keywords))[:10]
    
    def _detect_event_types(self, text: str) -> List[EventType]:
        """Detect types of events mentioned"""
        text_lower = text.lower()
        detected = []
        
        for event_type, patterns in self.event_patterns.items():
            if any(p in text_lower for p in patterns):
                detected.append(event_type)
        
        return detected
    
    def _extract_geography(self, entities: List[ExtractedEntity]) -> List[str]:
        """Extract geographic entities"""
        return [e.text for e in entities if e.label in ['GPE', 'LOC']]
    
    def _extract_timeframe(self, text: str) -> str:
        """Extract temporal context"""
        text_lower = text.lower()
        
        if any(w in text_lower for w in ['last week', 'recent', 'latest']):
            return "recent"
        elif any(w in text_lower for w in ['ongoing', 'continuous', 'keep']):
            return "ongoing"
        elif any(w in text_lower for w in ['upcoming', 'future', 'next']):
            return "future"
        
        return "ongoing"


# Convenience function
def parse_situation(text: str) -> ParsedSituation:
    """Parse a situation from text"""
    parser = SituationParser()
    return parser.parse(text)
