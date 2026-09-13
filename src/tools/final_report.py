from agent.messages import SystemMessage, HumanMessage
from agent.tool_decorator import tool

from llms.client_factory import ACTIVE_LLM_CLIENT


FINAL_REPORT_SYSTEM_PROMPT = """
You are an OSINT agent that helps exploring and investigating information about a person.
You have been given a case to investigate.
Generate a final report of the investigation.

When using, citing any information from the internet, you MUST ALWAYS cite the source.
When citing the source, you MUST ALWAYS cite the source URL, not just the domain name.
If there are many subpages, you MUST ALWAYS cite the source URLs of the subpages independently.
DO NOT MERGE THE CITATION OF THE SUBPAGES WITH THE SOURCE URL OF THE MAIN PAGE.
DO NOT FORGET TO INCLUDE THE HTTP/HTTPS PROTOCOL IN THE SOURCE URL.
When making any conclusion about the object, you must cite the sentence or image with URL to prove the conclusion.
The report should be in the following format (you may adapt it based on the information you have gathered):
- CASE BACKGROUND
- GENERAL OBJECTIVES
- LEGAL ISSUES
- INVESTIGATION PREPARATION
- OSINT STEPS
- FINDINGS
- CONCLUSION
- REFERENCES

At the very end, append a machine-readable benchmark payload in a fenced `json` block. Do not omit any of these four arrays, even when an array is empty:
```json
{
  "findings": [{"question": "...", "answer": "...", "supporting_entities": ["ENT-001"], "source_references": ["SRC-001"]}],
  "claims": [{"claim": "...", "source_references": ["SRC-001"]}],
  "reasoning_steps": [{"id": 1, "conclusion": "...", "premise_entities": ["ENT-001"], "premise_relations": ["trojanized"]}],
  "contradictions": [{"contradiction_id": "CONTRA-001", "description": "...", "source_references": ["SRC-001", "SRC-002"]}]
}
```
Use only entity and source identifiers supplied in the investigation context. Never invent identifiers or evidence. This JSON is required for automated evaluation; the Markdown report remains the human-readable companion.

For reasoning steps, `premise_entities` must contain exact entity IDs from the case context and `premise_relations` must contain exact canonical relation_type strings from the case context. Do not use prose descriptions such as "compromised build environment" or invent alternate identifiers.

If the investigation context contains required case questions or key findings, emit exactly one finding object for each question. Preserve the question text (minor paraphrase is acceptable), do not merge multiple questions into one finding, and include an evidence-based answer for every question. If evidence is insufficient, emit the finding with an explicit uncertainty statement and the supporting sources that justify that limitation.

Input format:
- You may receive either plain text, or a JSON-like text blob that includes sections such as:
  `case`, `scope`, `kb_entities`, `kb_edges`, `evidence_urls`, `notes`, `assumptions`.
- If the input includes KB entities/edges, treat them as ground truth context and reflect them in findings.

Only use this tool after the user has explicitly asked for a final report and confirmed they are ready to stop gathering new information.
"""


@tool
def final_report(investigation_summary: str) -> str:
    """Generate a structured OSINT final report from the investigation summary.

    This tool MUST only be called after the user explicitly asks for a final report
    and confirms they are ready to stop gathering additional information.
    """
    messages = [
        SystemMessage(content=FINAL_REPORT_SYSTEM_PROMPT),
        HumanMessage(content=investigation_summary),
    ]
    response = ACTIVE_LLM_CLIENT.invoke(messages)
    return getattr(response, "content", str(response))

