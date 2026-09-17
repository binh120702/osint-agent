# First comparison candidate: OpenOSINT

Status: selected for adaptation assessment; not executed or benchmark-qualified.
Date: 2026-09-17. No persistent goal created or changed.

## Identity and verified source

- Repository: https://github.com/OpenOSINT/OpenOSINT
- Pinned commit: `1ab71de6cdb1e6f5423c46e154b7a838b233aae2`
- Package version: 2.29.0; Python >=3.10.
- Local clean detached checkout: `outputs/candidate-runs/openosint/source/`.
- Included LICENSE contains MIT grant and copyright notice.
- `pyproject.toml` supplies optional Ollama and OpenAI-compatible backends.
- Stock Dockerfile uses Python 3.11, installs web dependencies and optional reconnaissance binaries, and starts a web service. It is not an offline benchmark image.
- 54 `test_*.py` files counted; tests have NOT been run.

Pinned evidence:
- https://github.com/OpenOSINT/OpenOSINT/blob/1ab71de6cdb1e6f5423c46e154b7a838b233aae2/README.md
- https://github.com/OpenOSINT/OpenOSINT/blob/1ab71de6cdb1e6f5423c46e154b7a838b233aae2/pyproject.toml
- https://github.com/OpenOSINT/OpenOSINT/blob/1ab71de6cdb1e6f5423c46e154b7a838b233aae2/LICENSE
- https://github.com/OpenOSINT/OpenOSINT/blob/1ab71de6cdb1e6f5423c46e154b7a838b233aae2/Dockerfile

## Why this candidate

It is an actual agent, not just a benchmark harness. Local inference support avoids mandatory cloud inference credentials; source and container packaging provide a plausible integration path. This is an engineering selection, not a claim that it is the strongest OSINT agent or already compatible with our corpus.

Its live identifier/reconnaissance tools are not equivalent to our frozen narrative evidence. Preserve its agent loop and label any tool/reporter adapter explicitly. Do not fabricate DNS/WHOIS responses from narrative pages, use synthetic intelligence, or silently replace the candidate with our agent.

## Local preflight observations

- Git: 2.54.0.windows.1.
- Docker client and active server: 29.5.3.
- GPU reported by nvidia-smi: NVIDIA GeForce RTX 5060 Ti, 16311 MiB.
- D: available disk approximately 95 GB.
- Ollama executable not found on PATH. No model-serving container visible; listed images were SearXNG and Neo4j. This does not establish absence of every possible model cache or service on the machine.
- No local model endpoint/weights verified.
- No candidate dependencies installed, container built, smoke test executed, model downloaded, or live target queried.

## Required decisions and comparison constraints

1. LLM inference is allowed for both agents, including the approved hosted provider used by our agent. A local runtime/model download is optional, not a prerequisite. Prefer the same provider/model and comparable inference budgets; verify historical model metadata rather than inferring it from current defaults.
2. Inspect candidate dispatch and agent loop to establish whether immutable search/content tools can be integrated without replacing its reasoning architecture. If not, report mismatch rather than manufacture compatibility.
3. Use an isolated runtime with approved LLM inference access only; investigation search/content must use immutable snapshots, with no live target collection. Do not mount the project's full `.env` or expose unrelated credentials to third-party code. Scope inference credentials or use a controlled inference proxy. This is offline evidence replay with hosted inference, not a fully network-isolated run.
4. Run one-case pilot first; preserve raw output and errors before any ten-case run.
5. Same-model runs of both agents are needed to isolate scaffold effects. Comparing a local-model candidate against the existing production-model baseline is a system comparison, confounded by model differences.
6. Keep structural validity separate from grounding. Missing graph fields must not be invented by an adapter. Retrieval remains `not_annotated` until reviewed qrels exist.

## Policy correction

The user clarified that comparison agents may use LLMs just as our own agent does. The prior local-only inference requirement is withdrawn. Missing Ollama is not a blocker. The inspected baseline manifest records `mode: offline` and `graph_source: trace` but does not record provider/model, so it cannot establish the historical model identity. The current client factory supports hosted providers; its defaults are not historical-run evidence. No persistent goal was changed.

The existing baseline and snapshots are unchanged. Further broad discovery is deferred per user request.
