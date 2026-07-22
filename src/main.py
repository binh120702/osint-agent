"""
OSINT Agent — entry point.

Run:
    uv run uvicorn server:app --reload --port 8000

Or directly:
    python main.py
"""
from dotenv import load_dotenv
load_dotenv()

import uvicorn

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)