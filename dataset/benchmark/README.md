# Benchmark Runner

The benchmark framework validates cases, replays offline source snapshots, runs the existing agent, captures tool traces, and scores extracted outputs.

From the repository root:

```powershell
uv run --project src python -m dataset.benchmark.runner --case case_001 --validate-only
```

The default case is `case_001`. A real run requires the normal LLM and Neo4j configuration:

```powershell
uv run --project src python -m dataset.benchmark.runner --case case_001 --mode offline
```

Results are written to `dataset/results/<run_id>/`. Offline mode replaces only search/content tools with case-snapshot replay. Live mode uses the normal production tools and is non-deterministic.
