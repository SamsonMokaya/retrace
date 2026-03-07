"""Nova Lite for RAG question-answering via Bedrock Converse API."""
import logging
import os

import boto3

logger = logging.getLogger(__name__)

NOVA_LITE_MODEL = "amazon.nova-lite-v1:0"


def _get_client():
    region = os.environ.get("AWS_REGION", "us-east-1")
    return boto3.client("bedrock-runtime", region_name=region)


def _format_events_for_prompt(events: list[dict]) -> str:
    """Group by URL + date (same page on the same day) so we don't merge different sessions."""
    by_key: dict[tuple[str, str], dict] = {}
    for e in events:
        url = (e.get("url") or "").strip()
        if not url:
            continue
        ts = e.get("timestamp") or ""
        date = ts.split("T")[0] if "T" in ts else (ts[:10] if len(ts) >= 10 else "")
        if not date:
            date = "(unknown date)"
        key = (url, date)
        ev_type = (e.get("type") or "").lower()
        if key not in by_key:
            by_key[key] = {"visit_title": None, "highlights": []}
        if ev_type == "highlight":
            text = (e.get("text") or "").strip()
            if text:
                excerpt = text[:500] + ("..." if len(text) > 500 else "")
                by_key[key]["highlights"].append(excerpt)
        else:
            title = (e.get("title") or "").strip() or "(no title)"
            if by_key[key]["visit_title"] is None:
                by_key[key]["visit_title"] = title
    if not by_key:
        return "(No relevant memories found.)"
    # Sort by date desc then url so recent / same-day groups are clear
    sorted_keys = sorted(by_key.keys(), key=lambda k: (k[1], k[0]), reverse=True)
    lines = []
    for (url, date), data in [(k, by_key[k]) for k in sorted_keys]:
        title = data["visit_title"] or "(page visited, no title)"
        lines.append(f"Page: {url} (date: {date})")
        lines.append(f"  Visited: {title}")
        if data["highlights"]:
            for i, h in enumerate(data["highlights"], 1):
                lines.append(f"  Highlighted on this page ({i}): {h}")
        else:
            lines.append("  Highlighted on this page: (none)")
        lines.append("")
    return "\n".join(lines).strip()


def answer_with_rag(question: str, events: list[dict], date_filter: str | None = None) -> str | None:
    """
    Call Nova Lite with the question and retrieved events. Returns answer text or None on failure.
    The model writes one chat-style answer and inserts markdown links [title](url) when citing pages.
    If date_filter is set, memories are already restricted to that day.
    """
    if not question or not question.strip():
        return None
    context = _format_events_for_prompt(events)
    date_note = ""
    if date_filter:
        date_note = f"\nThe memories below are restricted to {date_filter}. Answer only for that day.\n\n"
    user_content = f"""Use only the following memories from the user's browsing history. Memories are grouped by page (URL) and include a date. For each page you see: what they visited (title) and what they highlighted on that page.
{date_note}
Instructions:
- Answer in your own words. Be as helpful and natural as you like—no strict length or format. Your reply will be shown as chat-style text in a div.
- When you cite or mention a page the user visited or highlighted, embed it as a link so it's clickable. Use exactly this form: <a href="URL" target="_blank" rel="noopener">link text</a>. Use the exact URL from the memories. Any other text should be plain (no other HTML tags).
- For general questions (what can you do, help, how this works): answer freely in plain text. No links.
- For questions about their browsing: answer freely and, when you mention a page, use the link form above so it appears as an embedded link.
- FORBIDDEN: Never write "(no highlights)". Omit mention of highlights when there are none.
- If there are no relevant memories at all, say so. No links.

Memories (grouped by page):
{context}

Question: {question.strip()}

Answer:"""

    try:
        client = _get_client()
        response = client.converse(
            modelId=NOVA_LITE_MODEL,
            messages=[{"role": "user", "content": [{"text": user_content}]}],
            inferenceConfig={
                "maxTokens": 1024,
                "temperature": 0.3,
                "topP": 0.9,
            },
        )
        out = response.get("output", {})
        msg = out.get("message", {})
        content = msg.get("content") or []
        if not content:
            return None
        return content[0].get("text", "").strip() or None
    except Exception as e:
        logger.exception("Nova Lite RAG failed: %s", e)
        return None
