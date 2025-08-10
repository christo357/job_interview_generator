from jd2interview.skills.query import top_k_skills_for_role
from jd2interview.crawl.stackoverflow_requests import fetch_stackoverflow_requests
from jd2interview.crawl.pipeline import persist_questions
from jd2interview.utils.config import settings

def crawl_for_role(role_id: int):
    sites = [s.strip() for s in settings.CRAWL_SITES if s.strip()]
    skills = [s for s,_ in top_k_skills_for_role(role_id, k=8)]
    if not skills:
        return {"inserted": 0, "by_site": {}, "skills": []}
    totals, total = {}, 0
    for site in sites:
        items = list(fetch_stackoverflow_requests(
            site=site,
            tags_any=skills,                    # role-aware
            query=settings.CRAWL_QUERY_HINT,   # e.g., "interview"
            pages=settings.CRAWL_PAGES,
            page_size=settings.CRAWL_PAGE_SIZE,
        ))
        n = persist_questions(items)
        totals[site] = n; total += n
    return {"inserted": total, "by_site": totals, "skills": skills}

def crawl_for_role_stream(role_id: int):
    sites = [s.strip() for s in settings.CRAWL_SITES if s.strip()]
    skills = [s for s,_ in top_k_skills_for_role(role_id, k=8)]
    if not skills:
        yield "No skills for this role. Parse JD & build skill graph first."; return
    yield f"Skills: {skills}"
    total = 0
    for site in sites:
        yield f"Fetching {site} (tags_any={skills}, q={settings.CRAWL_QUERY_HINT!r}, pages={settings.CRAWL_PAGES}, page_size={settings.CRAWL_PAGE_SIZE})"
        items = list(fetch_stackoverflow_requests(
            site=site,
            tags_any=skills,
            query=settings.CRAWL_QUERY_HINT,
            pages=settings.CRAWL_PAGES,
            page_size=settings.CRAWL_PAGE_SIZE,
        ))
        n = persist_questions(items)
        total += n
        yield f"[{site}] upserted: {n}"
    yield f"Done. Total upserted: {total}"