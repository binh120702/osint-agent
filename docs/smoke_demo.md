## MVP smoke demo (local-only)

This is a quick end-to-end checklist to validate the MVP workflow:
case intake → tool calls → KB/KG updates → streaming text responses → report.

### Prerequisites

- Python **3.13** (see `src/.python-version`)
- `uv` installed
- Docker (with Neo4j and SearXNG containers running)
- Env: set API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY`) and `LLM_PROVIDER` in `src/.env`.

### 1) Start the FastAPI Server

From the repository root:

```bash
cd src
uv sync
uv run python main.py
```

Expected: Uvicorn starts the server on `http://localhost:8000`.

### 2) Open the Agent Chat UI

Open your web browser and navigate to:

`http://localhost:8000`

Expected: The dark-themed, glassmorphic OSINT Agent chat interface loads.

### 3) Run a Sample Case

In the chat input, paste the following prompt:

```text
Investigate this case:
- Target: “Yukon Bomber” (unknown individual)
- Goal: Find online profiles, websites, and any linked accounts or domains.

Start with web search. As you find URLs, deep search a small set of relevant pages. Periodically extract entities and relations into the knowledge base.
When you have enough, generate the final report.
```

Expected:
- The response starts streaming back text token-by-token immediately.
- As the agent triggers search or database actions, collapsible **Tool Call** elements (`⚙ engine_search_tool`, `⚙ knowledge_agent`, etc.) appear showing the arguments passed and outputs returned.

### 4) Validate KB/KG Updates

- Once the agent finishes executing the task, you can query the knowledge base endpoints to ensure entities/edges were written:
  - Check entities: `http://localhost:8000/api/kb/<thread_id>/entities`
  - Check relationships: `http://localhost:8000/api/kb/<thread_id>/edges`
- Or look directly in the local data directory: `src/data/<thread_id>/kb_entities.txt` and `src/data/<thread_id>/kb_edges.jsonl`.

### 5) Export the Report

- Once the final report tool is run, copy the markdown report from the final assistant message bubble and save it locally.

### Troubleshooting

- **Text doesn't stream**: Check the server terminal logs to see if there were connection timeouts or credentials errors with your LLM provider.
- **No knowledge base updates**: Ensure Neo4j is running in Docker and credentials (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`) in `src/.env` are correct.
