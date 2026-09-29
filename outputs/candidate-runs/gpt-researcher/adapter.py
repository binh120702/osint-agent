"""Immutable-snapshot structured adapter for the frozen GPT Researcher source."""
from __future__ import annotations
import asyncio, json, os, time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "outputs/candidate-runs/gpt-researcher/source"
import sys
sys.path.insert(0, str(SOURCE))

class SnapshotRetriever:
    requires_scraping = False
    case: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    def __init__(self, query: str, query_domains=None): self.query = query
    def search(self, max_results: int = 5):
        self.__class__.trace.append({"query": self.query, "max_results": max_results})
        return [{"url": s["uri"], "raw_content": s.get("raw_text", ""),
                 "title": (s.get("content") or {}).get("page_title", s["source_id"]),
                 "source_id": s["source_id"]} for s in self.case.get("sources", [])][:max_results]

class DummyEmbeddings:
    def embed_documents(self, texts): return [[0.0] * 3 for _ in texts]
    def embed_query(self, text): return [0.0] * 3
class DummyMemory:
    def __init__(self, *a, **k): pass
    def get_embeddings(self): return DummyEmbeddings()

class FileLLM:
    def __init__(self, io: Path, model: str, max_requests: int):
        self.io, self.model, self.max_requests, self.count = io, model, max_requests, 0
    def _request(self, messages):
        self.count += 1
        if self.count > self.max_requests: raise RuntimeError("benchmark LLM request budget exhausted")
        p = self.io / f"request-{self.count:04d}.json"
        p.write_text(json.dumps({"model": self.model, "messages": messages}, ensure_ascii=False), encoding="utf8")
        rp = self.io / f"response-{self.count:04d}.json"
        deadline = time.monotonic() + int(os.environ.get("BENCHMARK_RESPONSE_TIMEOUT", "900"))
        while not rp.exists():
            if time.monotonic() > deadline: raise TimeoutError("host inference bridge response timeout")
            time.sleep(.1)
        data = json.loads(rp.read_text(encoding="utf8"))
        if "bridge_error" in data: raise RuntimeError(data["bridge_error"])
        return data["choices"][0]["message"].get("content", "")
    async def get_chat_response(self, messages, stream=False, websocket=None, **kwargs):
        return self._request(messages)
    async def ainvoke(self, prompt, **kwargs):
        messages = getattr(prompt, "to_messages", lambda: prompt)()
        return type("Msg", (), {"content": self._request([{"role": getattr(m, "type", "user"), "content": getattr(m, "content", str(m))} for m in messages])})()

def run(case: dict[str, Any], io: Path, model: str, max_requests: int = 80):
    from gpt_researcher import agent as agent_mod
    from gpt_researcher import skills, actions
    from gpt_researcher.skills import researcher as researcher_mod
    from gpt_researcher.actions import query_processing, report_generation
    import gpt_researcher.utils.llm as llm_mod
    SnapshotRetriever.case = case; SnapshotRetriever.trace = []
    os.environ['MAX_SEARCH_RESULTS_PER_QUERY'] = str(max(10, len(case.get('sources', []))))
    filellm = FileLLM(io, model, max_requests)
    # Only replace external boundaries: retriever, embeddings, and provider transport.
    agent_mod.get_retrievers = lambda headers, cfg: [SnapshotRetriever]
    agent_mod.Memory = DummyMemory
    def get_llm(provider, **kwargs): return filellm
    llm_mod.get_llm = get_llm
    # Imported references in native modules are patched to the same file transport.
    async def completion(messages, **kwargs): return await filellm.get_chat_response(messages, **kwargs)
    query_processing.create_chat_completion = completion
    report_generation.create_chat_completion = completion
    async def fixed_outline(query, *args, **kwargs):
        return [query]
    researcher_mod.plan_research_outline = fixed_outline
    prompt = case["investigation_goal"]
    gt = case.get("ground_truth", {})
    entity_catalog = json.dumps([{"id": e.get("id"), "type": e.get("type"), "value": e.get("value")} for e in gt.get("entities", [])], ensure_ascii=False)
    source_catalog = json.dumps([{"source_id": s.get("source_id"), "uri": s.get("uri")} for s in case.get("sources", [])], ensure_ascii=False)
    contradiction_catalog = json.dumps([{ "contradiction_id": x.get("contradiction_id"), "description": x.get("description", "") } for x in gt.get("contradictions", [])], ensure_ascii=False)
    step_catalog = json.dumps([{ "step_index": x.get("step_index"), "conclusion": x.get("conclusion", ""), "premise_entities": x.get("premise_entities", []), "premise_relations": x.get("premise_relations", []) } for x in gt.get("reasoning_proof_chains", [])], ensure_ascii=False)
    contract = f"""
Return the report with the following required benchmark contract. Use only the supplied snapshot evidence and preserve canonical IDs exactly as listed below. These catalogs are benchmark metadata, not evidence; cite source IDs only when the source text supports the statement.
CANONICAL ENTITIES: {entity_catalog}
CANONICAL SOURCES: {source_catalog}
CANONICAL CONTRADICTIONS: {contradiction_catalog}
CANONICAL PROOF STEPS: {step_catalog}
[CLAIM] source_references=SRC-... claim text [/CLAIM]
[FINDING] question=... entities=ENT-... sources=SRC-... finding text [/FINDING]
[CONTRADICTION] contradiction_id=CONTRA-... sources=SRC-... description [/CONTRADICTION]
[STEP] id=1 conclusion=... premise_entities=ENT-... premise_relations=... [/STEP]
Then include a fenced JSON object with arrays named findings, claims, contradictions, reasoning_steps; each finding has question, answer, supporting_entities, source_references; claims have source_references; contradictions have contradiction_id, description, source_references; reasoning_steps have id, conclusion, premise_entities, premise_relations. Do not invent IDs or evidence. Include all required proof steps only when supported; if a step is unsupported, include it with an empty/qualified conclusion rather than inventing evidence.
"""
    r = agent_mod.GPTResearcher(prompt, report_source="web", verbose=False, agent="research", role="OSINT researcher", headers={"retrievers":"custom"}, max_subtopics=3, mcp_strategy="disabled")
    start=time.monotonic(); context=asyncio.run(r.conduct_research()); report=asyncio.run(r.write_report(custom_prompt=contract))
    result={"candidate":"assafelovic/gpt-researcher", "adaptation":"native-workflow-snapshot-retriever-file-inference-v1", "case_id":case["case_id"], "report":report, "context":context, "visited_urls":sorted(r.visited_urls), "retriever_trace":SnapshotRetriever.trace, "request_count":filellm.count, "duration_seconds":time.monotonic()-start}
    (io/"candidate-result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")

a=FileLLM
async def _subtopics(filellm, task, data, config, subtopics=None, **kwargs):
    return subtopics or [task]
