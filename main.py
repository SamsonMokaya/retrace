import html
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from chroma_store import add_event as chroma_add_event, clear_all as chroma_clear_all, count as chroma_count, search as chroma_search
from db import clear_events, get_events_by_ids, get_timeline, init_db, get_event_by_id, insert_event, list_events
from embeddings import EMBEDDING_MODEL, embed_text, embed_text_with_error
from llm import answer_with_rag
from schemas import MemoryEvent, MemoryEventCreate, QueryRequest, QueryResponse, SearchRequest, TimelineDay

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Retrace API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/dev/reset")
def dev_reset():
    """Clear all events from SQLite and Chroma. For local testing only."""
    clear_events()
    chroma_clear_all()
    return {"ok": True, "message": "All events and vectors deleted."}


def _text_to_embed(body: MemoryEventCreate) -> str:
    """Build searchable text for embedding (title + highlighted text or url)."""
    parts = []
    if body.title:
        parts.append(body.title)
    if body.text:
        parts.append(body.text)
    if not parts:
        parts.append(body.url)
    return " ".join(parts).strip() or body.url


# Never store page_visit events for the Retrace app (localhost / 127.0.0.1)
_EXCLUDED_VISIT_HOSTS = ("localhost", "127.0.0.1")


def _sanitize_answer_html(raw: str) -> str:
    """Allow only <a href="http(s)://...">text</a>; escape everything else so it is safe for innerHTML.
    Also converts markdown [text](url) to <a> in case the model outputs that instead of HTML."""
    if not raw or not raw.strip():
        return raw or ""
    # Fallback: convert markdown [text](url) to <a> so we support both LLM output styles
    raw = re.sub(
        r"\[([^\]]*)\]\((https?://[^)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        raw,
    )
    safe_links: list[str] = []
    def replace_link(m: re.Match) -> str:
        href, text = m.group(1).strip(), m.group(2)
        if href.startswith(("http://", "https://")):
            safe_links.append(
                '<a href="' + html.escape(href, quote=True) + '" target="_blank" rel="noopener">'
                + html.escape(text) + "</a>"
            )
            return f"\x00LINK{len(safe_links) - 1}\x00"
        return html.escape(m.group(0))
    pattern = re.compile(r'<a\s+href="([^"]+)"[^>]*>([^<]*)</a>', re.IGNORECASE)
    step1 = pattern.sub(replace_link, raw)
    step2 = html.escape(step1)
    for i, link in enumerate(safe_links):
        step2 = step2.replace(f"\x00LINK{i}\x00", link)
    return step2


def _is_excluded_visit_url(url: str) -> bool:
    if not url or not url.strip():
        return True
    try:
        host = urlparse(url).hostname or ""
        return host.lower() in _EXCLUDED_VISIT_HOSTS
    except Exception:
        return True


@app.post("/events", response_model=MemoryEvent)
def create_event(body: MemoryEventCreate):
    if body.type == "page_visit" and _is_excluded_visit_url(body.url):
        return Response(status_code=204)
    event_id = insert_event(
        type=body.type,
        url=body.url,
        timestamp=body.timestamp,
        title=body.title,
        text=body.text,
        metadata=body.metadata,
    )
    text_for_embed = _text_to_embed(body)
    embedding = embed_text(text_for_embed) if text_for_embed else None
    if embedding:
        chroma_add_event(event_id, embedding, metadata={"type": body.type, "url": body.url})
    event = get_event_by_id(event_id)
    if not event:
        raise HTTPException(status_code=500, detail="Event created but not found")
    return event


@app.get("/events", response_model=list[MemoryEvent])
def list_events_route(limit: int = 100):
    return list_events(limit=limit)


@app.get("/events/{event_id}", response_model=MemoryEvent)
def get_event(event_id: int):
    event = get_event_by_id(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.get("/embed-test")
def embed_test(text: str = "hello"):
    """Test Bedrock embedding: returns success or the exact error. Use ?text=something"""
    embedding, error = embed_text_with_error(text)
    if error:
        return {"ok": False, "embedding_model": EMBEDDING_MODEL, "error": error}
    return {"ok": True, "embedding_model": EMBEDDING_MODEL, "dimension": len(embedding)}


@app.get("/search/debug")
def search_debug():
    """Check why search might return empty: events in DB vs vectors in Chroma."""
    events = list_events(limit=1000)
    return {"events_in_db": len(events), "vectors_in_chroma": chroma_count()}


@app.post("/search", response_model=list[MemoryEvent])
def search_events(body: SearchRequest):
    """Semantic search: embed query, search Chroma, return matching events."""
    embedding = embed_text(body.query.strip())
    if not embedding:
        return []
    event_ids = chroma_search(embedding, top_k=body.limit)
    if not event_ids:
        return []
    return get_events_by_ids(event_ids)


@app.get("/timeline", response_model=list[TimelineDay])
def get_timeline_route(limit_days: int = 31):
    """Events grouped by day, most recent first. Optional ?limit_days=31."""
    return get_timeline(limit_days=limit_days)


def _events_for_date(events: list[dict], date: str) -> list[dict]:
    """Filter events to those on the given date (YYYY-MM-DD)."""
    if not date or not date.strip():
        return events
    want = date.strip()[:10]
    return [e for e in events if (e.get("timestamp") or "").startswith(want)]


def _parse_date_from_query(query: str) -> str | None:
    """Infer a single date (YYYY-MM-DD) from natural language like 'on the 6th', 'yesterday', 'march 5'. Returns None if no date found."""
    if not query or not query.strip():
        return None
    q = query.strip().lower()
    today = datetime.now().date()

    # yesterday / today
    if re.search(r"\byesterday\b", q):
        return (today - timedelta(days=1)).isoformat()
    if re.search(r"\btoday\b", q):
        return today.isoformat()

    # YYYY-MM-DD
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", q)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # "6th", "on the 6th", "the 6th" -> 6th of current month
    m = re.search(r"(?:on\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\b", q)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            try:
                return today.replace(day=day).isoformat()
            except ValueError:
                pass

    # month name + day: "march 6", "march 6th", "6 march", "6th of march"
    months = "january|february|march|april|may|june|july|august|september|october|november|december"
    m = re.search(rf"\b({months})\s+(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\b", q)
    if m:
        try:
            mon, day = m.group(1).capitalize(), m.group(2)
            dt = datetime.strptime(f"{mon} {day}", "%B %d")
            return dt.replace(year=today.year).date().isoformat()
        except ValueError:
            pass
    m = re.search(rf"\b(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({months})\b", q)
    if m:
        try:
            day, mon = m.group(1), m.group(2).capitalize()
            dt = datetime.strptime(f"{mon} {day}", "%B %d")
            return dt.replace(year=today.year).date().isoformat()
        except ValueError:
            pass

    return None


@app.post("/query", response_model=QueryResponse)
def query_events(body: QueryRequest):
    """RAG: semantic search + Nova Lite answer. Uses your memories to answer the question. Optional date=YYYY-MM-DD or date inferred from query (e.g. 'on the 6th', 'yesterday') restricts to that day."""
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    # Use explicit date from body or try to infer from query text so we filter and return empty sources when nothing that day
    effective_date = body.date or _parse_date_from_query(query)
    embedding = embed_text(query)
    event_ids = chroma_search(embedding, top_k=body.limit) if embedding else []
    events = get_events_by_ids(event_ids) if event_ids else []
    if effective_date:
        events = _events_for_date(events, effective_date)
        if not events:
            return QueryResponse(answer="There's nothing in your memory for that day.")
    answer = answer_with_rag(query, events, date_filter=effective_date)
    if answer is None:
        answer = "I couldn't generate an answer. Check that Nova Lite is enabled in Bedrock (Model access) and try again."
    answer = _sanitize_answer_html(answer)
    return QueryResponse(answer=answer)
