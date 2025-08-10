from typing import Literal, List, Dict
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from jd2interview.utils.config import settings

from sqlalchemy import select
from jd2interview.storage.db import session_scope, Question, QuestionMeta, upsert_question_meta
from jd2interview.retrieval.availability import _relevant_ids_for_role
# from jd2interview.enrich.metadata import classify_question  # reuse your existing one


QType = Literal["Behavioral","Technical","Coding","System Design"]
Diff  = Literal["Easy","Medium","Hard"]

class Rubric(BaseModel):
    signals: List[str] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    scoring: str = "0-5 rubric"

class QMeta(BaseModel):
    qtype: QType
    difficulty: Diff
    evaluation_rubric: Rubric

PROMPT = ChatPromptTemplate.from_template("""
Classify the interview question and return JSON with keys: qtype, difficulty, evaluation_rubric.
qtype ∈ ["Behavioral","Technical","Coding","System Design"]
difficulty ∈ ["Easy","Medium","Hard"]

Question Title:
{title}

Question Body (markdown):
```{body}```

Return ONLY the JSON.
""")

def classify_question(title: str, body: str) -> QMeta:
    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.0)
    chain = PROMPT | llm.with_structured_output(QMeta)
    return chain.invoke({"title": title, "body": body})


class Suitability(BaseModel):
    is_interview: bool = Field(..., description="true if this could be used in an interview")
    suggested_type: QType
    reason: str

SUIT_PROMPT = ChatPromptTemplate.from_template("""
Decide if the following StackExchange-style question is suitable as an interview question.
Return JSON with keys: is_interview (true/false), suggested_type, reason (short).
Types: ["Behavioral","Technical","Coding","System Design"].

Title:
{title}

Body (markdown):
```{body}```
""")

def interview_gate(title: str, body: str) -> Suitability:
    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.0)
    chain = SUIT_PROMPT | llm.with_structured_output(Suitability)
    return chain.invoke({"title": title, "body": body})


def classify_role_questions_stream(role_id: int, batch_size: int = 25, max_items: int | None = None):
    """
    Yields progress messages while classifying all relevant questions for this role
    that don't yet have QuestionMeta. Persists results so next runs are fast.
    """
    classified, skipped = 0, 0
    with session_scope() as db:
        ids_all = _relevant_ids_for_role(db, role_id, topk=8, limit=10000)
        if not ids_all:
            yield "No relevant web questions found for this role."
            return
        have_meta = {
            qid for (qid,) in db.execute(
                select(QuestionMeta.question_id).where(QuestionMeta.question_id.in_(ids_all))
            ).all()
        }
        targets = [qid for qid in ids_all if qid not in have_meta]
        if max_items is not None:
            targets = targets[:max_items]

        total = len(targets)
        yield f"Classifying {total} web questions…"
        for i in range(0, total, batch_size):
            chunk = targets[i:i+batch_size]
            for qid in chunk:
                q = db.get(Question, qid)
                if not q:
                    skipped += 1
                    continue
                title = (q.title or "").strip()
                body  = (q.body_markdown or q.body_html or "").strip()
                try:
                    meta = classify_question(title, body)
                    upsert_question_meta(db, qid, meta.qtype, meta.difficulty, meta.evaluation_rubric.model_dump())
                    classified += 1
                except Exception:
                    skipped += 1
            yield f"…{min(i+batch_size, total)}/{total} done (classified {classified}, skipped {skipped})"
    yield f"Done. Classified {classified}, skipped {skipped}."