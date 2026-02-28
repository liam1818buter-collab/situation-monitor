from transformers import pipeline


class Summarizer:
    def __init__(self):
        self.summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
    
    def summarize(self, text: str, max_length: int = 150) -> str:
        """Summarize text to max_length tokens"""
        if len(text) < 100:
            return text
        # Truncate if too long
        text = text[:1024]
        result = self.summarizer(text, max_length=max_length, min_length=30, do_sample=False)
        return result[0]['summary_text']
