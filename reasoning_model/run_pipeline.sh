#!/bin/sh
# Full ADABase pilot after features exist: train (single + agents/fusion) -> evidence -> LLM explanations
# -> evaluate -> LoRA.
# Needs: data/features/*.parquet, `ollama serve` running with qwen2.5:3b-instruct.
# Usage: sh run_pipeline.sh   (from reasoning_model/; logs to results/pipeline.log)
set -e
cd "$(dirname "$0")"
PY=.venv/bin/python
log() { echo "=== $* $(date +%H:%M)"; }

if [ -z "$SKIP_TRAIN" ]; then  # SKIP_TRAIN=1 resumes from the evidence stage with the saved models
log "train binary (Optuna)";  $PY src/train.py --task binary --tune
log "train 3class";           $PY src/train.py --task 3class
log "train tlx";              $PY src/train.py --task tlx
log "modality agents + fusion"; $PY src/fusion.py
fi
log "evidence";               $PY src/evidence.py --all; $PY src/evidence.py --all --fusion
N=${N:-10}  # windows per subject explained here; N=0 explains all (slow on CPU: ~2300 LLM calls)
log "explanations (Ollama, $N windows/subject)"
LIM=$([ "$N" -gt 0 ] && echo "--limit $N")
for f in results/evidence/*.jsonl; do s=$(basename "$f" .jsonl)
  $PY src/reasoner.py --subject "$s" $LIM | tail -1; $PY src/reasoner.py --subject "$s" --fusion $LIM | tail -1; done
log "evaluate + ablations";   $PY src/evaluate.py --ablations
log "LoRA build";             $PY src/finetune.py --build
log "LoRA train (Ollama stopped to free RAM)"
pkill -f "ollama serve" || true
$PY src/finetune.py --train
log "LoRA compare on held-out subjects"; $PY src/finetune.py --compare
log "pack hand-off for the test laptop -> results/handoff.tar.gz"
tar czf results/handoff.tar.gz data/features results/models results/lora results/evidence results/evidence_fusion \
    results/*.csv results/*.png 2>/dev/null || true
log "done"
