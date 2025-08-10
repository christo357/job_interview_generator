# src/jd2interview/generation/llm_qna.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

from jd2interview.utils.config import settings
from jd2interview.skills.query import top_k_skills_for_role
from jd2interview.storage.db import (
    SessionLocal,
    upsert_question_with_answers,
    upsert_question_meta,
    Question,
    Answer,
    Role,
)


# ---------------- Pydantic models (v2) ----------------

class EvaluationRubric(BaseModel):
    signals: List[str] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    scoring: str = ""


class GenQA(BaseModel):
    question: str
    type: str = Field(description='One of: "Coding", "Technical", "Behavioral"')
    difficulty: str = Field(description='One of: "Easy", "Medium", "Hard"')
    evaluation_rubric: EvaluationRubric
    tags: List[str] = Field(default_factory=list, description="Domains/skills, e.g., ['ml','oops','system design']")
    # optional
    answer: Optional[str] = None
    url: Optional[str] = None


class GenQABatch(BaseModel):
    items: List[GenQA] = Field(default_factory=list)


# ---------------- LLM + Prompt ----------------

def _llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.3,
        api_key=getattr(settings, "OPENAI_API_KEY", None),
    )


PROMPT = ChatPromptTemplate.from_template(
    """
You are generating interview questions tailored to a specific role.

Role: {role_title}
Top role skills/tags: {role_skills}
Target round: {target_type}
Requested count: {count}
Coding language (if Coding): {code_lang}
Difficulty policy: {difficulty_policy}
Restrict difficulty: {restrict_difficulty}

Rules:
- If restrict_difficulty is "Easy" / "Medium" / "Hard", set every item's difficulty exactly to that value.
- Technical = non-coding (concepts, debugging, systems, tradeoffs).
- Coding = clear problem statements (no full solutions; brief hints OK). Use {code_lang} terminology.
- Behavioral = STAR-style prompts tied to the role/skills.
- Make tags informative (e.g., ["ml", "transformers", "optimization"], ["oops", "design patterns"]).

Return ONLY JSON matching the provided schema.
"""
)


# ---------------- Persistence helpers ----------------

def _persist_generated(items: List[GenQA]) -> List[dict]:
    """
    Upsert generated questions into DB with source='generated', persist QuestionMeta,
    and (optionally) one Answer if the LLM included it.
    """
    out: List[dict] = []
    inserted = 0

    with SessionLocal() as db:
        for it in items:
            # Minimal object with attributes that upsert_question_with_answers expects
            class _Item:
                pass

            x = _Item()
            x.source = "generated"
            x.external_id = f"gen_{uuid4().hex}"
            x.url = it.url or ""
            x.title = (it.question or "").split("\n", 1)[0][:200]  # first line trims to title
            x.body_markdown = it.question or ""
            x.body_html = None
            x.tags = it.tags or []
            x.companies = []
            x.question_type = it.type
            x.difficulty = it.difficulty
            x.created_at = datetime.utcnow()
            x.score = 0
            x.hash = None
            x.answers = []  # <-- important: avoid AttributeError in DB helper

            q: Question = upsert_question_with_answers(db, x)
            upsert_question_meta(db, q.id, it.type, it.difficulty, it.evaluation_rubric.model_dump())

            # Optional single answer
            if it.answer:
                db.add(
                    Answer(
                        question_id=q.id,
                        external_id=f"gen_{uuid4().hex}_ans",
                        body_markdown=it.answer,
                        body_html=None,
                        score=0,
                        is_accepted=True,
                        created_at_source=datetime.utcnow(),
                    )
                )
                db.commit()

            inserted += 1
            out.append(
                {
                    "id": q.id,
                    "question": it.question,
                    "type": it.type,
                    "difficulty": it.difficulty,
                    "evaluation_rubric": it.evaluation_rubric.model_dump(),
                    "url": q.url,
                    "tags": it.tags,
                    "source": "generated",
                }
            )

    print(f"[LLM] persisted {inserted} generated questions → {settings.DB_URL}")
    return out


# ---------------- Public API ----------------

def generate_qna_for_role(
    role_id: int,
    target_type: str,
    count: int,
    difficulty_policy: str = "Mixed (let the model balance)",
    code_lang: str = "Python",
    persist: bool = True,
    restrict_difficulty: str = "",  # "", or "Easy"/"Medium"/"Hard"
) -> List[dict]:
    """
    Generate a batch of questions for a role, optionally persist, and return plain dicts.

    target_type: "Coding" | "Technical" | "Behavioral"
                  ("System Design" will be mapped to "Technical")
    """
    # Normalize type
    if target_type.lower() == "system design":
        target_type = "Technical"

    # Role context
    skills = [s for s, _ in top_k_skills_for_role(role_id, k=10)]
    with SessionLocal() as db:
        role_name = db.query(Role.name).filter(Role.id == role_id).scalar()
    role_title = role_name or (skills[0] if skills else f"Role {role_id}")

    print(
        f"[LLM] DB_URL={settings.DB_URL} | role_id={role_id} | role_title='{role_title}' | "
        f"target={target_type} | count={count} | restrict={restrict_difficulty or 'None'} | model={settings.OPENAI_MODEL}"
    )

    # Build chain
    llm = _llm()
    chain = PROMPT | llm.with_structured_output(GenQABatch, method="function_calling")

    # Invoke
    try:
        res: GenQABatch = chain.invoke(
            {
                "role_title": role_title,
                "role_skills": ", ".join(skills) or "software engineering",
                "target_type": target_type,
                "count": int(count),
                "code_lang": code_lang or "Python",
                "difficulty_policy": difficulty_policy,
                "restrict_difficulty": restrict_difficulty,
            }
        )
    except Exception as e:
        print(f"[LLM] invoke failed: {type(e).__name__}: {e}")
        return []

    items: List[GenQA] = list(res.items) if res and getattr(res, "items", None) else []
    print(f"[LLM] model returned {len(items)} items")

    if not items:
        return []

    # Persist or return
    return _persist_generated(items) if persist else [i.model_dump() for i in items]