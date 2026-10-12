#!/bin/sh
# Full ADABase pilot after features exist: train -> evidence -> LLM explanations -> evaluate -> LoRA.
# Needs: data/features/*.parquet, `ollama serve` running with qwen2.5:3b-instruct.
# Usage: sh run_pipeline.sh   (from reasoning_model/; logs to results/pipeline.log)
set -e
cd "$(dirname "$0")"
PY=.venv/bin/python
log() { echo "=== $* $(date +%H:%M)"; }

log "train binary (Optuna)";  $PY src/train.py --task binary --tune
log "train 3class";           $PY src/train.py --task 3class
log "train tlx";              $PY src/train.py --task tlx
log "evidence";               $PY src/evidence.py --all
log "explanations (Ollama)"
for f in results/evidence/*.jsonl; do $PY src/reasoner.py --subject "$(basename "$f" .jsonl)" | tail -1; done
log "evaluate + ablations";   $PY src/evaluate.py --ablations
log "LoRA build";             $PY src/finetune.py --build
log "LoRA train (Ollama stopped to free RAM)"
pkill -f "ollama serve" || true
$PY src/finetune.py --train
log "LoRA compare on held-out subjects"; $PY src/finetune.py --compare
log "done"
