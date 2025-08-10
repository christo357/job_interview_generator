import time
import requests
from requests import HTTPError

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional
from jd2interview.ingest.models import QuestionItem
from jd2interview.utils.config import settings

QUESTIONS_URL = "https://api.stackexchange.com/2.3/questions"
SEARCH_ADV_URL = "https://api.stackexchange.com/2.3/search/advanced"
UA = {"User-Agent": "jd2interview-crawler/0.1 (+demo)"}

def _params_base(site: str, with_body: bool) -> Dict:
    key = getattr(settings, "STACKEXCHANGE_KEY", "") or ""
    return {
        "order": "desc",
        "sort": "votes",
        "site": site,
        "filter": "withbody" if (with_body and key) else "default",
        "pagesize": getattr(settings, "CRAWL_PAGE_SIZE", 50),
        **({"key": key} if key else {}),
    }


def _fetch_page(url: str, params: Dict) -> Dict:
    r = requests.get(url, params=params, headers=UA, timeout=30)
    try:
        r.raise_for_status()
    except HTTPError as e:
        # Make debugging easier: include body text
        msg = f"{e} :: url={r.url} :: body={r.text[:300]}..."
        raise HTTPError(msg, response=r) from e
    return r.json()

def _to_item(d: Dict) -> QuestionItem:
    created = datetime.fromtimestamp(d.get("creation_date", 0), tz=timezone.utc)
    return QuestionItem(
        source="stackexchange",
        external_id=str(d.get("question_id")),
        url=d.get("link"),
        title=d.get("title") or "",
        body_markdown=d.get("body_markdown") or d.get("body"),
        body_html=d.get("body"),
        tags=d.get("tags") or [],
        companies=[],
        question_type=None,
        difficulty=None,
        created_at=created,
        score=d.get("score", 0),
        answers=[],
        # if your QuestionItem doesn't have `metadata`, remove the next line
        # metadata={"provider": "stackexchange"},
    )

def fetch_stackoverflow_requests(
    site: str = "stackoverflow",
    pages: int = 2,
    page_size: int = 50,
    # tags_all: Optional[List[str]] = None,
    tags_any: Optional[List[str]] = None,
    query: Optional[str] = None,
    with_body: bool = True,
    sleep_s: float = 0.2,
) -> Iterable[QuestionItem]:
    tags_all = [t.strip().lower() for t in (tags_all or []) if t and t.strip()]
    tags_any = [t.strip().lower() for t in (tags_any or []) if t and t.strip()] or [None]

    for any_tag in tags_any:
        base = _params_base(site, with_body, page_size)
        if tags_all:
            base["tagged"] = ";".join(tags_all + ([any_tag] if any_tag else []))
        elif any_tag:
            base["tagged"] = any_tag

        for page in range(1, pages + 1):
            params = {**base, "page": page}
            data = None

            if query:
                # 1st try: search/advanced with full-text 'q'
                try:
                    data = _fetch_page(SEARCH_ADV_URL, {**params, "q": query})
                except HTTPError:
                    # 2nd try: search/advanced with 'intitle'
                    try:
                        data = _fetch_page(SEARCH_ADV_URL, {**params, "intitle": query})
                    except HTTPError:
                        # 3rd try: plain /questions without query (just tags + votes)
                        data = _fetch_page(QUESTIONS_URL, params)
            else:
                data = _fetch_page(QUESTIONS_URL, params)

            items = data.get("items", [])
            for it in items:
                yield _to_item(it)

            if not data.get("has_more"):
                break
            time.sleep(sleep_s)