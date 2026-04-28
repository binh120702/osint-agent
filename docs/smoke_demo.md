## MVP smoke demo (local-only)

This is a quick end-to-end checklist to validate the MVP workflow:
case intake → tool calls → KB/KG updates → human-in-the-loop → report + export.

### Prerequisites

- Python **3.13** (see `src/.python-version`)
- `uv` installed
- Optional: Node.js + `pnpm` for the UI
- Env: set `OPENAI_API_KEY` in `src/.env`

### 1) Start the LangGraph server

From the repo root:

```bash
cd src
uv sync --frozen
uv run langgraph dev
```

Expected: server at `http://localhost:2024`, graph/assistant id `osint_agent`.

### 2) Start the Agent Chat UI

In a second terminal:

```bash
cd agent-chat-ui
pnpm install
pnpm dev
```

Open `http://localhost:3000`.

If prompted for settings, use:
- Deployment URL: `http://localhost:2024`
- Assistant / Graph ID: `osint_agent`

### 3) Run a sample case

In the chat, paste:

```text
Investigate this case:
- Target: “Yukon Bomber” (unknown individual)
- Goal: Find online profiles, websites, and any linked accounts or domains.

Start with web search. As you find URLs, deep search a small set of relevant pages. Periodically extract entities and relations into the knowledge base.
When you have enough, ask me whether to continue or generate the final report.
```

### 4) Validate KB/KG updates

- After the agent runs tools and finishes a response, open the **Knowledge Graph** panel (right side) and confirm:
  - Nodes/edges render (non-empty graph).
  - Graph refreshes after subsequent agent responses.

### 5) Use the HITL controls

At the bottom action bar:

- **Continue**: keeps you in “investigation mode” (focuses the input).
- **Generate report**: instructs the agent to produce a final report grounded in KB/KG.
- **Stop**: creates a new thread (or cancels if currently running).

### 6) Export the report

After a report is produced (latest assistant message):

- Click **Export** to copy the report to clipboard and download a `*.md` file.

### Troubleshooting

- **No knowledge graph**: ensure the agent called `kb_extract_relations` at least once; the KG panel reads `src/data/<threadId>/kb_edges.jsonl`.
- **UI can’t connect**: check `http://localhost:2024/info` and confirm assistant id is `osint_agent`.
- **Tool output too long**: adjust `OSINT_MAX_TOOL_CHARS` env var (server-side) if needed.

