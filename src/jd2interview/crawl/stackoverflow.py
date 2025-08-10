# import time
# import requests
# from datetime import datetime, timezone
# from typing import Dict, Iterable, List, Optional
# from jd2interview.ingest.models import QuestionItem
# from jd2interview.utils.config import settings

# QUESTIONS_URL = "https://api.stackexchange.com/2.3/questions"
# SEARCH_ADV_URL = "https://api.stackexchange.com/2.3/search/advanced"
# UA = {"User-Agent": "jd2interview-crawler/0.1 (+demo)"}

# def _params_base(site: str, with_body: bool) -> Dict:
#     p = {
#         "order": "desc",
#         "sort": "votes",
#         "site": site,
#         "filter": "withbody" if with_body else "default",
#         "pagesize": 50,
#     }
#     key = getattr(settings, "STACKEXCHANGE_KEY", "") or ""
#     if key:
#         p["key"] = key
#     return p

# def _fetch_page(url: str, params: Dict) -> Dict:
#     r = requests.get(url, params=params, headers=UA, timeout=30)
#     r.raise_for_status()
#     return r.json()

# def _to_item(d: Dict) -> QuestionItem:
#     created = datetime.fromtimestamp(d.get("creation_date", 0), tz=timezone.utc)
#     return QuestionItem(
#         source="stackexchange",                        # consistent source name
#         external_id=str(d.get("question_id")),        # no custom "so_" prefix needed
#         url=d.get("link"),
#         title=d.get("title") or "",
#         body_markdown=d.get("body_markdown") or d.get("body"),
#         body_html=d.get("body"),
#         tags=d.get("tags") or [],
#         companies=[],
#         question_type=None,                           # enrich later via LLM
#         difficulty=None,                              # enrich later via LLM
#         created_at=created,
#         score=d.get("score", 0),
#         answers=[],
#         metadata={"provider": "stackexchange"}        # optional free-form metadata
#     )

# def fetch_stackoverflow_requests(
#     site: str = "stackoverflow",
#     pages: int = 2,
#     tags_all: Optional[List[str]] = None,     # AND semantics
#     tags_any: Optional[List[str]] = None,     # OR fan-out: multiple passes
#     query: Optional[str] = None,              # free-text search (search/advanced)
#     with_body: bool = True,
#     sleep_s: float = 0.2
# ) -> Iterable[QuestionItem]:
#     tags_all = [t.strip() for t in (tags_all or []) if t and t.strip()]
#     tags_any = [t.strip() for t in (tags_any or []) if t and t.strip()] or [None]

#     for any_tag in tags_any:  # OR fan-out
#         base = _params_base(site, with_body)
#         if tags_all:
#             base["tagged"] = ";".join(tags_all + ([any_tag] if any_tag else []))
#         elif any_tag:
#             base["tagged"] = any_tag

#         for page in range(1, pages + 1):
#             params = {**base, "page": page}
#             if query:
#                 params_q = {**params, "q": query}
#                 data = _fetch_page(SEARCH_ADV_URL, params_q)
#             else:
#                 data = _fetch_page(QUESTIONS_URL, params)

#             items = data.get("items", [])
#             for it in items:
#                 yield _to_item(it)
#             if not data.get("has_more"):
#                 break
#             time.sleep(sleep_s)  # polite


# # import asyncio
# # from typing import AsyncIterator, Dict, Any, Optional
# # from datetime import datetime, timezone
# # from jd2interview.crawl.base import Fetcher, HttpClient, RateLimiter
# # from jd2interview.utils.config import settings

# # API_URL = "https://api.stackexchange.com/2.3/questions"

# # class StackOverflowFetcher(Fetcher):
# #     """Fetch interview-style questions from Stack Overflow via Stack Exchange API."""
# #     name = "stackoverflow"

# #     def __init__(self, pagesize: int = 50, max_pages: int = 5, tagged: Optional[str] = None, with_body: bool = True):
# #         self.pagesize = pagesize
# #         self.max_pages = max_pages
# #         self.tagged = tagged  # e.g., "interview;algorithm" or "system-design"
# #         self.with_body = with_body
# #         self.limiter = RateLimiter(rate_per_sec=2.0)

# #     async def fetch(self, **kwargs) -> AsyncIterator[Dict[str, Any]]:
# #         key = settings.__dict__.get("STACKEXCHANGE_KEY") or ""
# #         filter_param = "withbody" if self.with_body else "default"
# #         page = 1
# #         async with HttpClient() as http:
# #             while page <= self.max_pages:
# #                 await self.limiter.wait()
# #                 params = {
# #                     "order": "desc",
# #                     "sort": "votes",
# #                     "site": "stackoverflow",
# #                     "pagesize": self.pagesize,
# #                     "page": page,
# #                     "filter": filter_param,
# #                 }
# #                 if self.tagged:
# #                     params["tagged"] = self.tagged
# #                 if key:
# #                     params["key"] = key
# #                 data = await http.get_json(API_URL, params=params)
# #                 items = data.get("items", [])
# #                 for it in items:
# #                     yield it
# #                 if not data.get("has_more"):
# #                     break
# #                 page += 1
# #                 await asyncio.sleep(0.1)

# # def so_item_to_question(item: Dict[str, Any]) -> Dict[str, Any]:
# #     # Normalize StackOverflow item to QuestionItem dict fields (provider-agnostic)
# #     from jd2interview.ingest.models import QuestionItem, AnswerItem
# #     created = datetime.fromtimestamp(item.get("creation_date", 0), tz=timezone.utc)
# #     q = QuestionItem(
# #         source="stackoverflow",
# #         external_id=str(item.get("question_id")),
# #         url=item.get("link"),
# #         title=item.get("title") or "",
# #         body_markdown=item.get("body_markdown"),
# #         body_html=item.get("body"),
# #         tags=item.get("tags") or [],
# #         companies=[],
# #         question_type=None,    # can be enriched later (LLM classify)
# #         difficulty=None,       # N/A on SO; can estimate later
# #         created_at=created,
# #         score=item.get("score", 0),
# #         answers=[]
# #     )
# #     # answers via separate API call is possible; many responses are snippets in body
# #     return q.model_dump()