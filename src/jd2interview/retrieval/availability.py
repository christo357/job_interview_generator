from __future__ import annotations
import json
from collections import Counter
from typing import Dict, List, Tuple, Optional
from sqlalchemy import select
from jd2interview.skills.query import top_k_skills_for_role
from jd2interview.storage.db import SessionLocal, Question, QuestionMeta

def _rows_for_role(db, role_id: int, topk: int = 8, limit: int = 5000):
    skills = [s for s,_ in top_k_skills_for_role(role_id, k=topk)]
    if not skills:
        return []
    rows = db.execute(
        select(Question.id, Question.tags_json)
        .order_by(Question.score.desc(), Question.id.desc())
        .limit(limit)
    ).all()
    skillset = {s.lower() for s in skills}
    out_ids = []
    for qid, tj in rows:
        try:
            tags = {t.lower() for t in json.loads(tj or "[]")}
        except Exception:
            tags = set()
        if tags & skillset:
            out_ids.append(qid)
    return out_ids

def available_counts_for_role(role_id: int) -> Dict[str, int]:
    """Return counts per type in DB for this role (based on tag overlap)."""
    with SessionLocal() as db:
        ids = _rows_for_role(db, role_id)
        if not ids:
            return {"Behavioral":0,"Technical":0,"Coding":0,"System Design":0,"Total":0}
        rows = db.execute(
            select(QuestionMeta.qtype).where(QuestionMeta.question_id.in_(ids))
        ).scalars().all()
    c = Counter(rows)
    out = {k: c.get(k,0) for k in ["Behavioral","Technical","Coding","System Design"]}
    out["Total"] = sum(out.values())
    return out


# def fetch_typed_questions_for_role(
#     role_id: int,
#     qtype: Optional[str] = None,                # "Behavioral" | "Technical" | "Coding" | "System Design" | None (all)
#     sources: Optional[List[str]] = None,        # e.g., ["stackexchange","generated"] or None (all)
#     limit: int = 10000
# ) -> List[Dict]:
#     """
#     Return typed, role-relevant questions with metadata, persisted in DB.
#     Role relevance = tag overlap with top-k skills (same logic as availability).
#     """
#     from jd2interview.retrieval.availability import _relevant_ids_for_role
#     with SessionLocal() as db:
#         ids = _relevant_ids_for_role(db, role_id, topk=8, limit=limit)
#         if not ids:
#             return []
#         # Join Question + QuestionMeta
#         q = (
#             select(Question, QuestionMeta)
#             .join(QuestionMeta, QuestionMeta.question_id == Question.id)
#             .where(Question.id.in_(ids))
#             .order_by(Question.score.desc(), Question.id.desc())
#         )
#         rows = db.execute(q).all()

#     out = []
#     for Q, M in rows:
#         if qtype and M.qtype != qtype:
#             continue
#         if sources and Q.source not in sources:
#             continue
#         try:
#             rubric = json.loads(M.rubric_json or "{}")
#         except Exception:
#             rubric = {}
#         try:
#             tags = json.loads(Q.tags_json or "[]")
#         except Exception:
#             tags = []
#         out.append({
#             "id": Q.id,
#             "question": (Q.title or "") + ("\n\n" + (Q.body_markdown or Q.body_html or "") if (Q.body_markdown or Q.body_html) else ""),
#             "type": M.qtype,
#             "difficulty": M.difficulty,
#             "evaluation_rubric": rubric,
#             "url": Q.url,
#             "tags": tags,
#             "source": Q.source,
#         })
#     return out

def fetch_typed_questions_for_role(
    role_id: int,
    qtype: Optional[str] = None,
    sources: Optional[List[str]] = None,
    limit: int = 10000,
) -> List[Dict]:
    out: List[Dict] = []
    with SessionLocal() as db:
        ids = relevant_question_ids_for_role(db, role_id, topk=8, limit=limit)
        if not ids:
            return out
        q = (
            select(Question, QuestionMeta)
            .join(QuestionMeta, QuestionMeta.question_id == Question.id)
            .where(Question.id.in_(ids))
            .order_by(Question.score.desc(), Question.id.desc())
        )
        for Q, M in db.execute(q).all():
            if qtype and M.qtype != qtype:
                continue
            if sources and Q.source not in sources:
                continue
            try:
                rubric = json.loads(M.rubric_json or "{}")
            except Exception:
                rubric = {}
            try:
                tags = json.loads(Q.tags_json or "[]")
            except Exception:
                tags = []
            out.append({
                "id": Q.id,
                "question": (Q.title or "") + (
                    "\n\n" + (Q.body_markdown or Q.body_html or "")
                    if (Q.body_markdown or Q.body_html) else ""
                ),
                "type": M.qtype,
                "difficulty": M.difficulty,
                "evaluation_rubric": rubric,
                "url": Q.url,
                "tags": tags,
                "source": Q.source,
            })
    return out

def relevant_question_ids_for_role(
    db, role_id: int, topk: int = 8, limit: int = 10000
) -> List[int]:
    """
    Return IDs of questions whose tags overlap with the role's top-k skills.
    This is our 'role relevance' filter used by classification, counts, and retrieval.
    """
    skills = [s for s, _ in top_k_skills_for_role(role_id, k=topk)]
    if not skills:
        return []
    wanted = {s.lower() for s in skills}

    rows = db.execute(
        select(Question.id, Question.tags_json)
        .order_by(Question.score.desc(), Question.id.desc())
        .limit(limit)
    ).all()

    ids: List[int] = []
    for qid, tj in rows:
        try:
            tags = {t.lower() for t in json.loads(tj or "[]")}
        except Exception:
            tags = set()
        if tags & wanted:
            ids.append(qid)
    return ids

# (optional) keep the old private name as an alias so other code continues to work
_relevant_ids_for_role = relevant_question_ids_for_role