# Four-Approach Comparison

This document summarizes the common contract-track evaluation.

## Results: completed-output view

| Approach | Finding F1 | Contradiction F1 | Reasoning | Report quality | Source precision | Source recall |
|---|---:|---:|---:|---:|---:|---:|
| **Baseline v15** | 0.9167 | 0.7333 | **0.9708** | **0.9500** | **1.0000** | **1.0000** |
| **OpenOSINT v6** | **0.9500** | 0.4711 | 0.8360 | 0.8725 | 0.9800 | 0.9083 |
| **GPT Researcher** | 0.4393 | **0.8167** | 0.5385 | 0.8417 | **1.0000** | 0.9639 |
| **Open Deep Research** | 0.2333 | 0.6000 | 0.6397 | 0.6833 | 0.9000 | 0.9000 |

## Results: valid-only view

This view includes only outputs that passed the structured validity checks.

| Approach | Finding F1 | Contradiction F1 | Reasoning | Report quality | Source precision | Source recall |
|---|---:|---:|---:|---:|---:|---:|
| **Baseline v15** | 0.9167 | 0.7333 | **0.9708** | **0.9500** | **1.0000** | **1.0000** |
| **OpenOSINT v6** | **0.9430** | 0.5475 | 0.8062 | 0.8871 | 0.9737 | 0.8958 |
| **GPT Researcher** | 0.4393 | **0.8167** | 0.5385 | 0.8417 | **1.0000** | 0.9639 |
| **Open Deep Research** | 0.2916 | 0.5000 | 0.7106 | 0.6771 | 0.8750 | 0.8750 |

## Simple summary

- **Best overall balance:** Baseline v15
- **Best finding score:** OpenOSINT v6
- **Best contradiction score:** GPT Researcher
- **Best reasoning score:** Baseline v15
- **Best report quality:** Baseline v15
- **Best source precision:** Baseline v15 and GPT Researcher
- **Best source recall:** Baseline v15

## Reliability

| Approach | Completed outputs | Valid outputs | Terminal failures | Validity rate |
|---|---:|---:|---:|---:|
| **Baseline v15** | 10 | 10 | 0 | 100.00% |
| **OpenOSINT v6** | 98 | 74 | 2 | 75.51% |
| **GPT Researcher** | Historical single-run artifacts | Not separately reported | Not separately reported | Not directly comparable |
| **Open Deep Research** | Historical single-run artifacts | Not separately reported | Not separately reported | Not directly comparable |

## Important limitations

- This is a **benchmark-aware contract track**, not a fully blind open-ended OSINT test.
- The prompt provides entities, required questions, proof-chain structure, and expected-answer scaffolding.
- Retrieval quality and semantic truth were not independently annotated.
- GPT Researcher and Open Deep Research use preserved historical single-run artifacts, so their reliability is not directly comparable to the multi-run evaluations.
- Scores should be read as benchmark results, not proof of general OSINT superiority.

## Reproducibility

Common scorer:

```text
outputs/score_common_contract_track.py
```

Common aggregate files:

```text
outputs/multi-iteration-runs/baseline-v15-structured-contract/scoring/common-contract-aggregate.json
outputs/multi-iteration-runs/openosint-v6-contract-10workers/scoring/common-contract-aggregate.json
outputs/candidate-runs/gpt-researcher/scoring/common-contract-aggregate.json
outputs/candidate-runs/open-deep-research/scoring/common-contract-aggregate.json
```
