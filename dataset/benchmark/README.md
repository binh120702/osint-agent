# Benchmark Runner

The benchmark framework validates cases, audits real-source provenance, replays immutable source snapshots, runs the existing agent, captures tool traces, and scores extracted outputs. It never treats LLM-generated text as a source.

From the repository root:

```powershell
uv run --project src python -m dataset.benchmark.runner --case case_001 --validate-only

# Audit that every case source is a real, human-reviewed public snapshot
python dataset/scripts/audit_provenance.py --strict
```

The default case is `case_001`. A real run requires the normal LLM and Neo4j configuration:

```powershell
uv run --project src python -m dataset.benchmark.runner --case case_001 --mode offline
```

Results are written to `dataset/results/<run_id>/`. Offline mode replaces only search/content tools with case-snapshot replay. Live mode uses the normal production tools and is non-deterministic. Offline mode is deterministic with respect to source availability, but the production LLM and Neo4j remain external dependencies unless a benchmark-specific client and graph backend are supplied.

Final-report scoring requires explicit annotations rather than broad prose overlap. Finding matching uses answer similarity with one-to-one matching, so paraphrased investigative questions are allowed. Reasoning reports precision, recall, and F1 over valid proof-step IDs and separately reports invalid IDs. Traceability checks source availability and claim/finding coverage. Quality includes structured-output validity and finding/traceability thresholds; it is not a writing-style or factuality score.

Required annotations:

```text
[CLAIM sources=SRC-001,SRC-002] evidence-backed claim [/CLAIM]
[FINDING question="exact case question" entities=ENT-001,ENT-002 sources=SRC-001] answer [/FINDING]
[CONTRADICTION id=CONTRA-001 sources=SRC-001,SRC-002] conflict and reconciliation [/CONTRADICTION]
[STEP id=1] evidence and conclusion [/STEP]
```

Only sources actually returned by benchmark tools are eligible for citations. Report quality is scored with a deterministic rubric. Use `--graph-source trace` for reproducible scoring from captured tool output; `--graph-source neo4j` is explicit and fails if Neo4j cannot be queried, rather than silently falling back.

For deterministic regression runs, provide a recorded model fixture:

```powershell
uv run --project src python -m dataset.benchmark.runner --case case_001 --mode recorded --llm-fixture dataset/fixtures/case_001.json --graph-source trace
```

The recorded client fails when its fixture is exhausted and never contacts an API. Run the mechanical case-quality gate with:

```powershell
uv run --project src python -m dataset.benchmark.case_quality --strict
```
