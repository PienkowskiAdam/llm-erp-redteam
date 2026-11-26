#!/usr/bin/env bash
# One-shot setup + run. Safe to re-run (idempotent).
# Usage:   ./run.sh
# Options: MODEL=qwen2.5:3b TRIALS=10 ./run.sh
set -euo pipefail

cd "$(dirname "$0")"
REPO_DIR="$(pwd)"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
TRIALS="${TRIALS:-5}"

say()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m    OK: %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

OS="$(uname -s)"
[[ "$OS" == "Darwin" || "$OS" == "Linux" ]] || die "Unsupported OS: $OS. On Windows use WSL (Ubuntu) and run this script inside it."

# ---------- 1. Python >= 3.10 ----------
say "1/6 Checking Python >= 3.10"
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [[ -z "$PY" ]]; then
  if [[ "$OS" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
    say "Installing Python 3.12 via Homebrew"
    brew install python@3.12
    PY="$(brew --prefix)/bin/python3.12"
  else
    die "Python 3.10+ not found. macOS: install Homebrew (https://brew.sh) then re-run. Linux: sudo apt install python3 python3-venv"
  fi
fi
ok "$($PY --version) ($PY)"

LLM_BACKEND="${LLM_BACKEND:-ollama}"
[[ "$LLM_BACKEND" == "lmstudio" ]] && LLM_BACKEND="openai"
OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://localhost:1234/v1}"
export LLM_BACKEND OPENAI_BASE_URL

if [[ "$LLM_BACKEND" == "openai" ]]; then
# ---------- 2-4 (OpenAI-compatible: LM Studio / vLLM / LiteLLM) ----------
say "2/6 Backend: OpenAI-compatible at $OPENAI_BASE_URL (Ollama steps skipped)"
say "3/6 Checking server"
MODELS_JSON="$(curl -fsS "$OPENAI_BASE_URL/models" 2>/dev/null)" || die "No server at $OPENAI_BASE_URL. LM Studio: open app -> Developer tab -> Start Server, and load a model. If server runs on another port (see 'lms server start' output), re-run with OPENAI_BASE_URL=http://localhost:<port>/v1"
ok "server up"
say "4/6 Selecting model"
if [[ -z "${MODEL:-}" ]]; then
  MODEL="$(printf '%s' "$MODELS_JSON" | "$PY" -c 'import json,sys; d=json.load(sys.stdin)["data"]; print(next((m["id"] for m in d if "embed" not in m["id"]), ""))')"
  [[ -n "$MODEL" ]] || die "Server has no chat model loaded. Load one in LM Studio (e.g. qwen3 / gpt-oss) and re-run."
fi
ok "model $MODEL"
export MODEL
else
# ---------- 2. Ollama installed ----------
say "2/6 Checking Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  if [[ "$OS" == "Darwin" ]]; then
    command -v brew >/dev/null 2>&1 || die "Homebrew missing. Install from https://brew.sh or download Ollama app from https://ollama.com/download, then re-run."
    brew install ollama
  else
    curl -fsSL https://ollama.com/install.sh | sh
  fi
fi
ok "$(ollama --version 2>/dev/null | head -1)"

# ---------- 3. Ollama server running ----------
say "3/6 Making sure Ollama server is running at $OLLAMA_URL"
if ! curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  nohup ollama serve >"${TMPDIR:-/tmp}/ollama.log" 2>&1 &
  for i in $(seq 1 30); do
    curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1 && break
    sleep 1
    [[ $i -eq 30 ]] && die "Ollama did not start in 30s. See ${TMPDIR:-/tmp}/ollama.log"
  done
fi
ok "server up"

# ---------- 4. Pick + pull model ----------
say "4/6 Selecting model"
if [[ -z "${MODEL:-}" ]]; then
  if [[ "$OS" == "Darwin" ]]; then RAM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
  else RAM_GB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 / 1024 )); fi
  if (( RAM_GB >= 12 )); then MODEL="qwen2.5:7b"; else MODEL="qwen2.5:3b"; fi
  ok "RAM ${RAM_GB} GB -> $MODEL"
fi
export MODEL OLLAMA_URL
ollama pull "$MODEL"
ok "model $MODEL ready"
fi

# ---------- 5. venv + tests ----------
say "5/6 Python venv + policy tests (no LLM)"
[[ -d .venv ]] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet pytest
python -m pytest -q || die "Policy tests failed. Do NOT continue; paste output above."
ok "tests passed"

# ---------- 6. Attack harness ----------
say "6/6 Running attacks: model=$MODEL trials=$TRIALS (takes a few minutes)"
mkdir -p results
OUT="results/$(date +%Y%m%d-%H%M%S)_${MODEL//[:\/]/-}.txt"
{
  echo "model=$MODEL trials=$TRIALS date=$(date -u +%FT%TZ) host_os=$OS"
  python -m harness.run --trials "$TRIALS"
} 2>&1 | tee "$OUT"

say "DONE. Results saved to $REPO_DIR/$OUT"
