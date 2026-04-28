# Agent Chat UI setup

The [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui) is a Next.js app that talks to the OSINT LangGraph server. The UI is included as the **`agent-chat-ui`** submodule.

**If you just cloned the repo**, fetch the submodule:

```bash
git submodule update --init --recursive
```

**Prerequisites:** Node.js and [pnpm](https://pnpm.io/) installed. Python and the LangGraph server are set up per the [README](../README.md).

---

## Run the stack

### 1. Start the LangGraph server

From the repo root (see [README – Running the agent](../README.md#running-the-agent)):

```bash
cd src
uv run langgraph dev
```

Server: **http://localhost:2024** · Graph ID: **`osint_agent`**

### 2. Configure the Agent Chat UI (optional)

To bypass the setup form, set the following environment variables:

```bash
NEXT_PUBLIC_API_URL=http://localhost:2024
NEXT_PUBLIC_ASSISTANT_ID=osint_agent
```

### 3. Install UI dependencies and start the app

```bash
cd agent-chat-ui
pnpm install
pnpm dev
```
You have to install node js and pnpm to run the UI.

Open **http://localhost:3000**. The app uses `.env` or the setup form.

Alternatively, use the public demo [agentchat.vercel.app](https://agentchat.vercel.app/) and enter your server URL and **`osint_agent`** when the server is running.

---

## Quick reference

| Item              | Value |
|-------------------|--------|
| Graph / Assistant ID | `osint_agent` |
| LangGraph server  | `http://localhost:2024` (when running `langgraph dev` from `src`) |
| UI app            | Next.js in `agent-chat-ui/` (port 3000) |

