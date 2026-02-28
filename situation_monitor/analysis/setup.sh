#!/bin/bash
# Download required models
echo "Downloading spaCy model..."
python -m spacy download en_core_web_sm

echo "Downloading HuggingFace models (first run will cache)..."
python -c "from transformers import pipeline; pipeline('sentiment-analysis', model='distilbert-base-uncased-finetuned-sst-2-english')"
python -c "from transformers import pipeline; pipeline('summarization', model='facebook/bart-large-cnn')"

echo "Setup complete!"
