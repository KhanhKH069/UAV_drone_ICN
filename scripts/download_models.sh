#!/usr/bin/env bash
# scripts/download_models.sh
# Download AI models cần thiết trước khi chạy `make up`
# Chạy một lần trên Edge Server.

set -e
MODELS_DIR="${MODELS_DIR:-./models-cache}"
mkdir -p "$MODELS_DIR/whisper" "$MODELS_DIR/nllb"

echo "📦 UAV_drone_ICN — Model Downloader"
echo "  Models dir: $MODELS_DIR"
echo ""

# ─────────────────────────────────────────────
# 1. Faster-Whisper
# ─────────────────────────────────────────────
echo "⏳ [1/2] Downloading Faster-Whisper large-v3..."
python3 -c "
from faster_whisper import WhisperModel
model = WhisperModel('large-v3', device='cpu', compute_type='int8', download_root='$MODELS_DIR/whisper')
print('✅ Whisper large-v3 downloaded')
"

# ─────────────────────────────────────────────
# 2. NLLB-200 Translation
# ─────────────────────────────────────────────
echo "⏳ [2/2] Downloading NLLB-200-distilled-600M..."
python3 -c "
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
model_name = 'facebook/nllb-200-distilled-600M'
AutoTokenizer.from_pretrained(model_name, cache_dir='$MODELS_DIR/nllb')
AutoModelForSeq2SeqLM.from_pretrained(model_name, cache_dir='$MODELS_DIR/nllb')
print('✅ NLLB-200 downloaded')
"

echo ""
echo "🎉 All models downloaded to $MODELS_DIR"
echo "   You can now run: make up"
