# OSINT Investigator Agent

An Open Source Intelligence (OSINT) agent built from scratch with a custom lightweight agent framework (no LangGraph or LangChain). It investigates targets using web search, deep site crawling, Pinterest scraping, Wikipedia/GitHub lookups, image description, and other tools, and dynamically maintains a Neo4j knowledge base graph. 

It runs as a FastAPI server and serves an interactive dark-mode HTML chat interface directly.

## Prerequisites

- **Python 3.13** (see `src/pyproject.toml` and `src/.python-version`)
- **Docker Desktop** (to run local Neo4j database and SearXNG search engine)
- **API Key** (OpenAI, Anthropic, or Gemini) based on your chosen provider

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/binh120702/osint-agent.git
cd osint-agent
```

### 2. Set up local Docker services (Neo4j and SearXNG)

The agent uses **Neo4j** as its storage engine for the knowledge base, and a local **SearXNG** instance to query search engines resiliently without bot blocks.

Start the services using Docker:

```bash
# 1. Run Neo4j Database
docker run -d --name neo4j-osint -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:latest

# 2. Run SearXNG Metasearch Engine (mounting the custom JSON settings configuration)
docker run -d --name searxng-osint -p 8080:8080 -v <absolute_path_to_workspace>/src/config/searxng_settings.yml:/etc/searxng/settings.yml searxng/searxng:latest
```

*Note: Replace `<absolute_path_to_workspace>` with the absolute path of the repository on your host machine.*

### 3. Install Python dependencies

Set up a virtual environment and install dependencies using `uv` (recommended):

```bash
cd src
uv sync
```

### 4. Configure Environment Variables

Copy the example environment file and configure your API keys:

```bash
cp src/.env.example src/.env
# Edit src/.env and configure your LLM_PROVIDER and corresponding API key
```

Required settings in `.env`:
```env
LLM_PROVIDER=openai   # Or "claude" / "gemini"
OPENAI_API_KEY=sk-... # If provider is openai
# or ANTHROPIC_API_KEY / GOOGLE_API_KEY
```

---

## Running the Agent

Start the FastAPI application from the **`src`** directory:

```bash
cd src
uv run python main.py
```

This starts the Uvicorn server on **http://localhost:8000**. Open this URL in your web browser to start using the OSINT Agent chat interface.

---

## MVP Smoke Demo

For a quick end-to-end validation of the workflow (web search → entity extraction → knowledge graph updates → streaming responses), see [docs/smoke_demo.md](docs/smoke_demo.md).

---

## Project Structure

```
osint-agent/
├── README.md                 # This file
├── docs/                     # Documentation (architecture overview, smoke demo)
├── src/
│   ├── main.py               # Application entry point (runs FastAPI/Uvicorn)
│   ├── server.py             # FastAPI routing and SSE streaming endpoints
│   ├── pyproject.toml        # Build configuration and dependencies
│   ├── requirements.txt      # Python dependencies list
│   ├── agent/                # Custom agent framework:
│   │   ├── messages.py       # Message objects (System, Human, AI, Tool)
│   │   ├── tool_decorator.py # Lightweight @tool decorator & JSON schema generator
│   │   └── loop.py           # Custom agent execution and streaming loop
│   ├── llms/                 # Direct SDK clients (OpenAI, Claude, Gemini)
│   ├── tools/                # Agent tools: search, web crawler, final report, KB/Neo4j graph
│   ├── static/               # HTML/CSS assets for the self-hosted Chat UI
│   └── crawlers/             # Helper scraping adapters
```