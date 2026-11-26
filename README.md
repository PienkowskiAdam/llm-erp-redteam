# llm-erp-redteam

Small testbed for the **LLM → ERP trust boundary**. An inbound customer email (untrusted) is processed
by an LLM agent that can change real orders. The repo includes the attacks, a way to measure them, and the fix.

All data is synthetic. Models run locally via Ollama.

## Threat model

| Asset | Attacker | Goal |
|---|---|---|
| Orders in ERP (qty, ship address) | Anyone who can send an email or attach a document | Change another tenant's order, redirect a shipment, sabotage quantities |

Trust boundary: everything in the email body or attachments is **data**. Sender identity comes only from the transport layer.

## Pipelines

- **vulnerable**: one LLM reads the email *and* holds the ERP tools. This is the typical "agent" demo.
- **hardened**:
  1. A quarantined LLM with **no tools** extracts a strict JSON intent.
  2. `app/policy.py` authorizes it deterministically: the sender's domain must own the order, `qty` is validated, large changes and all address changes go to a human.
  3. Plain code executes the change.

  The design assumes the extractor **will** be compromised. The security property is in the policy, not the prompt.
- **hardened-v1**: the hardened pipeline without step 0 below. Kept so the report can show the A6 gap before and after the fix.
- step 0 of **hardened** — provenance filter (`app/sanitize.py`): only text the sender visibly authored reaches the extractor. Hidden HTML, quoted/forwarded threads and attachment text are dropped. Attachments can inform a human, but they never drive actions.

## Attacks (`attacks/emails.json`)

| id | vector |
|---|---|
| A1 | direct instruction override, cross-tenant |
| A2 | hidden HTML comment / white text, address redirect |
| A3 | spoofed authority in forwarded thread |
| A4 | injection inside extracted attachment text |
| A5 | lookalike sender domain |
| A6 | legit sender, attachment injection moves own order within threshold (residual risk of v1) |
| B1 | benign control (false-positive check) |

## Run

One command (installs Ollama + model if missing, runs tests and harness):

```bash
bash run.sh                       # options: MODEL=qwen2.5:3b TRIALS=10 bash run.sh
```

Windows (Ollama, default):

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1            # options: -Model qwen2.5:3b -Trials 5 -OllamaUrl http://localhost:11434
```

Windows (LM Studio instead):

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Backend lmstudio -BaseUrl http://localhost:1234/v1
```

Manual:

```bash
python -m venv .venv && source .venv/bin/activate
pip install pytest
ollama pull qwen2.5:7b

pytest -q                                  # policy tests, no LLM
python -m harness.run --trials 5           # ASR table: vulnerable vs hardened
MODEL=llama3.1:8b python -m harness.run    # compare models
```

## Results

See `REPORT.md`.

## Roadmap

- Attack generator: a local model mutates the seed attacks (paraphrase, encoding, language switch), keeps the variants that succeed, and loops.
- Fine-tune a small attacker model on the successful variants (LoRA).
- Real email parsing (MIME, HTML→text, PDF) as an extra injection surface.
- DKIM/SPF verification instead of a domain string match.
