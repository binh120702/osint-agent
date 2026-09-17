"""Prepare the assisted OSINT-001 pilot input for the adapted candidate."""
from __future__ import annotations
import json
from pathlib import Path

case_path = Path('dataset/cases/case_001_3cx_cascading_supply_chain.json')
case = json.loads(case_path.read_text(encoding='utf-8'))
gt = case['ground_truth']
prompt = (
    "Investigate this benchmark case using only evidence returned by the immutable benchmark tools, then return the complete final report. Do not ask whether to continue. "
    f"Goal: {case['investigation_goal']} Target: {case['target']}\n\n"
    "Do not invent facts. Include readable Markdown and explicit benchmark annotations using these exact markers:\n"
    "[CLAIM sources=SRC-001,SRC-002] one evidence-backed claim [/CLAIM]\n"
    "[FINDING question=\"exact case question\" entities=ENT-001,ENT-002 sources=SRC-001] answer [/FINDING]\n"
    "[CONTRADICTION id=CONTRA-001 sources=SRC-001,SRC-002] conflicting claims and reconciliation [/CONTRADICTION]\n"
    "[STEP id=1] evidence and conclusion for proof step [/STEP]\n"
    "Cite only source IDs returned by tools. Label allegations, assessments, and uncertainty. End with a fenced JSON object containing exactly these arrays: findings, claims, reasoning_steps, contradictions. Each finding must have question, answer, supporting_entities, source_references; each claim must have claim and source_references; each reasoning step must have id, conclusion, premise_entities, premise_relations; each contradiction must have contradiction_id, description, source_references. Use exact ENT-* IDs and exact canonical relationship_type strings. Emit one finding for every required question. The canonical reference is output-format assistance, not evidence. Verify every conclusion against tool-returned source text.\n"
    "\nCANONICAL ENTITY REFERENCE:\n" + "\n".join(f"{x['id']} = {x['type']}: {x['value']}" for x in gt.get('entities', []))
    + "\nALLOWED RELATION TYPES:\n" + ", ".join(x['relationship_type'] for x in gt.get('relations', []))
    + "\nREQUIRED REASONING STEPS (copy exact premise IDs and relation strings; verify conclusions from tool evidence):\n" + "\n".join(
        f"STEP {x['step_index']}: entities={','.join(x['premise_entities'])}; relations={','.join(x['premise_relations'])}; conclusion={x['conclusion']}"
        for x in gt.get('reasoning_proof_chains', []))
    + "\nRequired case questions:\n- " + "\n- ".join(x['question'] for x in gt.get('key_findings', []))
)
out = Path('outputs/candidate-runs/openosint/runs/OSINT-001')
out.mkdir(parents=True, exist_ok=True)
spec = {'case_id': case['case_id'], 'case_sha256': __import__('hashlib').sha256(case_path.read_bytes()).hexdigest(), 'model': 'gpt-5.6-luna', 'max_requests': 20, 'sources': [{'source_id': s['source_id'], 'uri': s['uri'], 'raw_text': s.get('raw_text', ''), 'content': {'page_title': (s.get('content') or {}).get('page_title', s['source_id'])}} for s in case['sources']], 'prompt': prompt}
(out / 'input').mkdir(exist_ok=True)
(out / 'io').mkdir(exist_ok=True)
(out / 'input/case.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
print(out)
