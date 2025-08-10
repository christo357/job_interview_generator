# add near imports
from typing import List, Dict, Tuple
import numpy as np, json, random
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

from jd2interview.skills.query import top_k_skills_for_role
from jd2interview.storage.db import (
    session_scope, get_questions_with_any_tags,
    get_or_none_question_vector, upsert_question_vector,
    get_or_none_question_meta, upsert_question_meta
)
from jd2interview.retrieval.embeddings import embed_texts
from jd2interview.enrich.metadata import classify_question, interview_gate
from jd2interview.utils.config import settings

# ---------- existing helpers (keep) ----------
def _canon(text: str) -> str: return (text or "").strip()
def _q_repr(q: Dict) -> str: return f"{q['title']}\n\n{q['body_md']}"
def _build_query_text(role_title: str, skills: List[Tuple[str, float]]) -> str:
    s = ", ".join(s for s,_ in skills[:8]) or ""
    return f"Role: {role_title}\nTop skills: {s}\nGoal: find interview questions that assess these."
def _cosine(a, b): denom=(np.linalg.norm(a)*np.linalg.norm(b)) or 1e-8; return float(np.dot(a,b)/denom)

def _ensure_vectors(db, qs: List[Dict]) -> np.ndarray:
    texts, idxs, vecs = [], [], []
    for q in qs:
        qv = get_or_none_question_vector(db, q["id"])
        if qv:
            vecs.append(np.array(json.loads(qv.embedding_json), dtype=np.float32))
        else:
            texts.append(_q_repr(q)); idxs.append(q["id"]); vecs.append(None)
    if idxs:
        new_vecs = embed_texts(texts)
        for qid, emb in zip(idxs, new_vecs):
            upsert_question_vector(db, qid, emb)
        pos = 0
        for i, v in enumerate(vecs):
            if v is None:
                vecs[i] = np.array(new_vecs[pos], dtype=np.float32); pos += 1
    return np.vstack(vecs) if vecs else np.zeros((0, 1536), dtype=np.float32)

def _ensure_meta(db, qid: int, title: str, body: str) -> Dict:
    qm = get_or_none_question_meta(db, qid)
    if qm:
        try: rubric = json.loads(qm.rubric_json or "{}")
        except Exception: rubric = {}
        return {"type": qm.qtype, "difficulty": qm.difficulty, "evaluation_rubric": rubric}
    meta = classify_question(title, body)
    upsert_question_meta(db, qid, meta.qtype, meta.difficulty, meta.evaluation_rubric.model_dump())
    return {"type": meta.qtype, "difficulty": meta.difficulty, "evaluation_rubric": meta.evaluation_rubric.model_dump()}

# ---------- LLM fallback generator ----------
class GenQ(BaseModel):
    question: str
    type: str
    difficulty: str
    evaluation_rubric: Dict = Field(default_factory=dict)

FALLBACK_PROMPT = ChatPromptTemplate.from_template("""
Generate {count} interview questions for the role below. Return ONLY a JSON array of objects with keys:
question, type (Behavioral|Technical|Coding|System Design), difficulty (Easy|Medium|Hard), evaluation_rubric (JSON).

Role: {role_title}
Top skills: {skills_csv}
Target type: {target_type}
Guidelines:
- Make them realistic and concise.
- Ensure they assess the listed skills where relevant.
""")

def ensure_minimums(picked, min_per_type, role_title, skills):
    from collections import Counter
    have = Counter([p["type"] for p in picked])
    adds = []
    for t, m in min_per_type.items():
        need = max(0, m - have.get(t, 0))
        if need > 0:
            adds.extend(llm_generate(role_title, skills, need, t))  # uses your existing fallback
    # wrap generated items like retrieved
    adds = [{**g, "source": "generated", "url": None, "tags": []} for g in adds]
    return picked + adds


def llm_generate(role_title: str, skills: List[Tuple[str,float]], need: int, target_type: str) -> List[Dict]:
    if need <= 0: return []
    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.3)
    chain = FALLBACK_PROMPT | llm.with_structured_output(List[GenQ])  # type: ignore
    skills_csv = ", ".join(s for s,_ in skills[:8])
    out = chain.invoke({"count": need, "role_title": role_title, "skills_csv": skills_csv, "target_type": target_type})
    return [q.model_dump() for q in out][:need]

# ---------- distribution resolver (you already added earlier) ----------
def resolve_distribution(total: int, dist: Dict[str, int], flexible: bool = True):
    total = int(max(0, total))
    keys = list(dist.keys())
    vals = {k: max(0, int(dist[k])) for k in keys}
    s = sum(vals.values())
    if not flexible:
        if s != total: raise ValueError(f"Counts ({s}) do not equal total ({total}).")
        return vals, total, "strict_ok"
    if s == total: return vals, total, "ok"
    if s < total:
        rem = total - s
        for _ in range(rem): vals[random.choice(keys)] += 1
        return vals, total, "filled"
    return vals, s, "raised"

# ---------- main: build package + stats + fallback ----------
def build_interview_package(
    role_id: int,
    total_q: int = 5,
    per_type_target: Dict[str, int] | None = None,
    allow_fallback: bool = True,
) -> Dict:
    per_type_target = per_type_target or {"Behavioral":1,"Technical":2,"Coding":1,"System Design":1}
    stats = {"requested_total": total_q, "per_type_target": dict(per_type_target), "candidates": 0,
             "after_gate": 0, "per_type_available": {"Behavioral":0,"Technical":0,"Coding":0,"System Design":0}}

    skills = top_k_skills_for_role(role_id, k=8)  # [(skill, weight)]
    role_title = "Role"

    with session_scope() as db:
        candidates = get_questions_with_any_tags(db, [s for s,_ in skills], limit=1200)
        stats["candidates"] = len(candidates)
        if not candidates:
            return {"package": [], "stats": stats}

        qvec = np.array(embed_texts([_build_query_text(role_title, skills)])[0], dtype=np.float32)
        M = _ensure_vectors(db, candidates)

        sims = M @ (qvec / (np.linalg.norm(qvec) or 1e-8))
        order = np.argsort(-sims)

        picked: List[Dict] = []
        counts = {k:0 for k in per_type_target.keys()}

        # First pass: gate + count availability
        gated = []
        for idx in order:
            q = candidates[int(idx)]
            title = _canon(q["title"]); body = _canon(q["body_md"])
            try:
                gate = interview_gate(title, body)
                if not gate.is_interview:
                    continue
            except Exception:
                # if gate call fails, conservatively keep it
                pass
            gated.append(q)
        stats["after_gate"] = len(gated)

        # Peek meta types to know availability (cheap cache)
        type_cache = {}
        for q in gated[:400]:  # limit classification for stats
            meta = _ensure_meta(db, q["id"], _canon(q["title"]), _canon(q["body_md"]))
            type_cache[q["id"]] = meta["type"]
            stats["per_type_available"][meta["type"]] = stats["per_type_available"].get(meta["type"], 0) + 1

        # Second pass: pick to fill target per type
        for q in gated:
            if len(picked) >= total_q: break
            meta = type_cache.get(q["id"]) or _ensure_meta(db, q["id"], _canon(q["title"]), _canon(q["body_md"]))["type"]
            if counts.get(meta, 0) < per_type_target.get(meta, 0):
                picked.append({
                    "question": f"{_canon(q['title'])}\n\n{_canon(q['body_md'])}",
                    "type": meta,
                    "difficulty": _ensure_meta(db, q["id"], _canon(q["title"]), _canon(q["body_md"]))["difficulty"],
                    "evaluation_rubric": _ensure_meta(db, q["id"], _canon(q["title"]), _canon(q["body_md"]))["evaluation_rubric"],
                    "source": "retrieved",
                    "url": q["url"],
                    "tags": q["tags"],
                })
                counts[meta] += 1

        # Third pass: top-up regardless of type
        i = 0
        while len(picked) < total_q and i < len(gated):
            q = gated[i]; i += 1
            meta = type_cache.get(q["id"]) or _ensure_meta(db, q["id"], _canon(q["title"]), _canon(q["body_md"]))["type"]
            item = {
                "question": f"{_canon(q['title'])}\n\n{_canon(q['body_md'])}",
                "type": meta,
                "difficulty": _ensure_meta(db, q["id"], _canon(q["title"]), _canon(q["body_md"]))["difficulty"],
                "evaluation_rubric": _ensure_meta(db, q["id"], _canon(q["title"]), _canon(q["body_md"]))["evaluation_rubric"],
                "source": "retrieved",
                "url": q["url"],
                "tags": q["tags"],
            }
            # avoid exact duplicates
            if not any(item["url"] == p.get("url") and item["question"] == p["question"] for p in picked):
                picked.append(item)

        # Fallback to LLM if still short
        shortfall = total_q - len(picked)
        if shortfall > 0 and allow_fallback:
            # fill via types that are underfilled first
            need_by_type = {t: max(0, per_type_target.get(t,0) - sum(1 for p in picked if p["type"]==t))
                            for t in per_type_target}
            types_order = sorted(need_by_type.items(), key=lambda kv: -kv[1])
            for t, need in types_order:
                if shortfall <= 0: break
                gen = llm_generate(role_title, skills, min(shortfall, max(0, need)), t)
                for g in gen:
                    picked.append({**g, "source": "generated", "url": None, "tags": []})
                shortfall = total_q - len(picked)
            # still short? fill any type
            if shortfall > 0:
                gen = llm_generate(role_title, skills, shortfall, target_type=random.choice(list(per_type_target.keys())))
                for g in gen:
                    picked.append({**g, "source": "generated", "url": None, "tags": []})

        stats["produced"] = len(picked)
        stats["shortfall"] = max(0, total_q - len(picked))
        min_per_type = {"Behavioral": 5, "Technical": 5, "Coding": 5, "System Design": 5}
        picked = ensure_minimums(picked, min_per_type, role_title, skills)
        return {"package": picked[:total_q], "stats": stats}