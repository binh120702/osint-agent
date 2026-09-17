"""Network-free OpenOSINT adapter. No upstream source files are modified."""
from __future__ import annotations
import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace


def main():
    import openai
    from openai.types.chat import ChatCompletion
    import openosint.agent as upstream
    from replay import SourceReplay

    spec = json.loads(Path('/input/case.json').read_text())
    io = Path('/io')
    replay = SourceReplay({'sources': spec['sources']})
    calls = []
    request_count = 0

    async def create(**kwargs):
        nonlocal request_count
        request_count += 1
        if request_count > spec['max_requests']:
            raise RuntimeError('benchmark LLM request budget exhausted')
        stem = f'request-{request_count:04d}'
        kwargs.update(model=spec['model'], temperature=0, max_tokens=4096)
        temp = io / (stem + '.tmp')
        temp.write_text(json.dumps(kwargs, ensure_ascii=False))
        temp.rename(io / (stem + '.json'))
        response_path = io / (stem.replace('request', 'response') + '.json')
        deadline = time.monotonic() + 240
        while not response_path.exists():
            if time.monotonic() > deadline:
                raise TimeoutError('host inference bridge response timeout')
            await asyncio.sleep(.1)
        response = json.loads(response_path.read_text())
        if 'bridge_error' in response:
            raise RuntimeError(response['bridge_error'])
        return ChatCompletion.model_validate(response)

    # Only the SDK transport is substituted. The upstream run loop, tool-message
    # handling, stop-on-no-tool behavior and error handling remain unchanged.
    openai.AsyncOpenAI = lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    async def search(args):
        result = replay.search(args['query'], args.get('page', 1), args.get('page_size', 10))
        calls.append({'name': 'engine_search_tool', 'arguments': args, 'result': result})
        persist()
        return result

    async def fetch(args):
        result = replay.fetch(args['url'])
        calls.append({'name': 'get_url_content', 'arguments': args, 'result': result})
        persist()
        return result

    def persist():
        (io / 'tool-trace.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2))

    definitions = [
        {'name': 'engine_search_tool', 'description': 'Search only immutable public source snapshots for this case. Returns source IDs, URLs and snippets; use get_url_content for full evidence.', 'input_schema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer'}, 'page_size': {'type': 'integer'}}, 'required': ['query']}},
        {'name': 'get_url_content', 'description': 'Read full immutable source text by its URL returned by search. Unknown URLs fail; no live fetching.', 'input_schema': {'type': 'object', 'properties': {'url': {'type': 'string'}}, 'required': ['url']}}
    ]
    upstream._TOOL_MAP = {'engine_search_tool': search, 'get_url_content': fetch}
    upstream._OPENAI_TOOLS = upstream._to_ollama_tools(definitions)
    upstream.SYSTEM_PROMPT += '\n\nBENCHMARK ADAPTATION: Only engine_search_tool and get_url_content are available. Replace the live discovery/fetch strategy above with these immutable-source tools. Do not attempt live reconnaissance. Follow the user-specified report contract instead of the default section template. There is no final_report tool: return the full final report as your final assistant response. Never treat the canonical reference or required conclusions as evidence; verify against tools.'
    agent = upstream.OpenAICompatibleAgent(model=spec['model'], base_url='http://disabled.invalid/v1', api_key='no-credential')
    start = time.monotonic()
    response = asyncio.run(agent.run(spec['prompt']))
    result = {'candidate': 'OpenOSINT', 'adaptation': 'snapshot-tools-file-inference-transport-v1', 'content': response.content, 'error': response.error, 'tool_calls': calls, 'request_count': request_count, 'duration_seconds': time.monotonic() - start, 'query_trace': replay.query_trace}
    (io / 'candidate-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'complete': not bool(response.error), 'requests': request_count, 'tool_calls': len(calls), 'report_chars': len(response.content), 'error': response.error}))
    if response.error:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
