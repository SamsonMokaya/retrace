# Retrace

AI memory for your browsing: capture page visits and highlights, then ask questions in natural language. Uses semantic search (Chroma) and Amazon Bedrock (Nova Lite for chat, Titan for embeddings).

## Problem

People consume huge amounts of information online every day. We open dozens or hundreds of tabs, read articles, highlight text, and explore different topics. However, traditional browser history only stores URLs and timestamps. It does not capture meaning, context, or what we actually learned from those pages.

Bookmarks require manual saving and organization, and many useful insights are lost because users forget where they saw something.

As a result, valuable knowledge from browsing disappears quickly and becomes difficult to rediscover later.

## Solution

Retrace turns browsing activity into an AI-powered memory system. Instead of just storing URLs like browser history, it captures page visits and highlights, indexes them using semantic embeddings, and allows users to query their browsing history using natural language.

This means users can ask questions like:

- “What did I read about vector databases last week?”
- “What did I highlight about AI agents?”
- “What pages did I visit yesterday?”

Retrace then searches through stored browsing data and returns relevant pages with context.

## What Makes Retrace Different

**Traditional browser history:**

- Only stores URLs and timestamps
- Cannot be searched semantically
- Cannot answer questions about past browsing

**Retrace:**

- Stores browsing events as structured knowledge
- Uses embeddings for semantic search
- Allows natural language queries over browsing activity
- Links answers directly to the original pages

## Prerequisites

- **Python 3.10+**
- **A Chromium-based browser** (Chrome, Edge, Brave, etc.) for the extension
- **AWS** account with Bedrock access:
  - **Nova Lite** (`amazon.nova-lite-v1:0`) enabled in Model access (for Q&A)
  - **Titan Text Embeddings V2** (`amazon.titan-embed-text-v2:0`) enabled (for semantic search)

## Project structure

- **Retrace** (this repo) — Single project at root:
  - `main.py`, `db.py`, `llm.py`, `chroma_store.py`, `embeddings.py`, `schemas.py` — FastAPI app, storage, RAG
  - `static/query.html` — Query UI (single page, no build step)
  - `extension/` — Browser extension (Manifest V3): records page visits and highlights

## Setup

### 1. Run the server (from project root)

Clone or open the project, then from the **retrace** directory:

```bash
cd retrace
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy the example env file and add your AWS credentials:

```bash
cp .env.example .env
# Edit .env: set AWS_BEARER_TOKEN_BEDROCK and AWS_REGION
```

Run the server:

```bash
uvicorn main:app --reload --port 8000
```

- API: http://localhost:8000
- Query UI: http://localhost:8000/static/query.html
- Docs: http://localhost:8000/docs

### 2. Browser extension

1. Open your browser’s **extensions** page (e.g. **chrome://extensions**, **edge://extensions**, **brave://extensions**).
2. Turn **Developer mode** on (toggle usually in the top-right).
3. Click **Load unpacked** (or equivalent).
4. Select the **`extension`** folder inside the retrace project.
5. The Retrace icon should appear; click it to set the API URL (default `http://localhost:8000` when the server runs locally).

**Usage**

- **Page visits** — Automatically recorded when you finish loading a page (http/https). Visits to the Retrace app (localhost) are not stored.
- **Highlights** — Select text, then **Ctrl/Cmd+Shift+H** or right-click → **Save to Retrace**

### 3. Query

Open http://localhost:8000/static/query.html and ask in natural language, e.g.:

- “What did I visit today?”
- “What did I look at on the 6th?”
- “What did I highlight about Chroma?”

Answers are chat-style with embedded links when the model cites a page.

## Environment variables

| Variable                   | Description                                             |
| -------------------------- | ------------------------------------------------------- |
| `AWS_BEARER_TOKEN_BEDROCK` | Optional; use if not relying on IAM/CLI profile         |
| `AWS_REGION`               | AWS region for Bedrock (e.g. `us-east-1`, `eu-north-1`) |
| `EMBEDDING_MODEL`          | Optional; `titan` (default) or `nova`                   |

## Dev / reset

To clear all stored events and vectors (local only):

```bash
curl -X POST http://localhost:8000/dev/reset
```

## Future work

Retrace is currently a local, single-user prototype designed for demo purposes. Some directions for future iterations:

- **Accounts and sync**
  - Add authentication and per-user accounts so each person has their own history instead of a shared local database.
  - Host the backend so history can be accessed from anywhere (not just the machine where it was recorded).

- **Smarter memory selection**
  - Use Nova to decide whether a given page is worth storing at all, based on its content (for example: skip login/password-reset flows, payment pages, generic search results, error pages, and obviously sensitive content).
  - Always store explicit user highlights, even if the rest of the page is discarded.
  - Avoid repetition by de‑duplicating pages that are effectively the same as ones already stored so the memory stays focused on new information.

- **Richer context and summaries**
  - Generate short summaries of important pages to provide lightweight context when answering questions, while still respecting the privacy/sensitivity filters above.
  - Let users control how much of a page (full text vs. short summary vs. only highlights) is kept in their long-term browsing memory.

## License

Use and modify as you like.
