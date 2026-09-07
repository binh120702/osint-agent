"""Deterministic retrieval metrics for reviewed case topics."""
from __future__ import annotations
import math
from typing import Any

def score_retrieval(case: dict[str, Any], traces: list[dict[str, Any]]) -> dict[str, Any]:
    topics = case.get('retrieval_topics', [])
    if not topics: return {'status':'not_annotated','topics':0}
    ranked=[]
    for trace in traces:
        for item in trace.get('tool_calls', []):
            if item.get('name') == 'engine_search_tool':
                result=item.get('result','')
                if isinstance(result,str):
                    import json
                    try: ranked.extend(json.loads(result).get('merged_results', []))
                    except Exception: pass
    ids=[]
    for x in ranked:
        sid=x.get('source_id') if isinstance(x,dict) else None
        if sid and sid not in ids: ids.append(sid)
    details=[]
    for topic in topics:
        relevant=set(topic.get('relevant_sources',[])); hits=[x for x in ids if x in relevant]
        details.append({'topic_id':topic['topic_id'],'recall':len(hits)/len(relevant) if relevant else 0.0,'required_source_recall':len(hits)/len(relevant) if relevant else 0.0})
    return {'status':'scored','topics':len(details),'mean_recall':sum(x['recall'] for x in details)/len(details),'details':details}
