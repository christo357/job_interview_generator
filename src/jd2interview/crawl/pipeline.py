import asyncio
from typing import Iterable, Dict, Any, List
from jd2interview.ingest.models import QuestionItem
from jd2interview.storage.db import session_scope, upsert_question_with_answers, canonical_question_text, sha256_hex
from jd2interview.crawl.stackoverflow_requests import fetch_stackoverflow_requests

# normalize -> dedupe -> persist

def normalize_question(d: Dict[str, Any]) -> QuestionItem:
    # Here you can strip HTML to markdown, collapse whitespace, etc. For now pass-through.
    return QuestionItem(**d)

def dedupe_key(q: QuestionItem) -> str:
    return sha256_hex(canonical_question_text(q.title, q.body_markdown))

def persist_questions(items: Iterable[QuestionItem]) -> int:
    n = 0
    with session_scope() as db:
        for q in items:
            if not q.hash:
                q.hash = dedupe_key(q)
            upsert_question_with_answers(db, q)
            n += 1
    return n

def run_stackoverflow_requests(site: str, tags_all, tags_any, query, pages: int, pagesize:int) -> int:
    items = list(fetch_stackoverflow_requests(site=site, tags_any=tags_any, query=query, pages=pages, pagesize=pagesize))
    return persist_questions(items)