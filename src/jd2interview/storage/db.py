from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
from datetime import datetime
from typing import Optional, Iterable, Tuple
from sqlalchemy import (
    create_engine, String, Integer, Float, Text, ForeignKey,
    UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine.url import make_url
from sqlalchemy import DateTime, JSON, Boolean
from sqlalchemy import select




from jd2interview.utils.config import settings

# # --- Engine / Session ---
# engine = create_engine(settings.DB_URL, future=True, pool_pre_ping=True)

def _ensure_sqlite_dir(db_url: str):
    try:
        url = make_url(db_url)
    except Exception:
        return
    if url.drivername.startswith("sqlite") and url.database:
        p = Path(url.database)
        if not p.is_absolute():
            p = Path.cwd() / p
        p.parent.mkdir(parents=True, exist_ok=True)

def _create_engine():
    _ensure_sqlite_dir(settings.DB_URL)
    return create_engine(settings.DB_URL, future=True, pool_pre_ping=True)

engine = _create_engine()


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,   # <-- important
)


class Base(DeclarativeBase):
    pass

# --- ORM models ---
class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)

class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    canonical_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class SkillAlias(Base):
    __tablename__ = "skill_aliases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(255))
    __table_args__ = (UniqueConstraint("skill_id", "alias", name="uq_skill_alias"),)

class SkillEdge(Base):
    __tablename__ = "skill_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    dst_skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    relation_type: Mapped[str] = mapped_column(String(32))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[Optional[str]] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint("src_skill_id","dst_skill_id","relation_type", name="uq_edge"),)

class RoleSkill(Base):
    __tablename__ = "role_skills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    __table_args__ = (UniqueConstraint("role_id", "skill_id", name="uq_role_skill"),)

class Tool(Base):
    __tablename__ = "tools"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)

class SkillTool(Base):
    __tablename__ = "skill_tools"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"))
    relation_type: Mapped[str] = mapped_column(String(32), default="uses_tool")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[Optional[str]] = mapped_column(String(32))
    __table_args__ = (UniqueConstraint("skill_id","tool_id","relation_type", name="uq_skill_tool"),)

Index("ix_edges_src", SkillEdge.src_skill_id)
Index("ix_edges_dst", SkillEdge.dst_skill_id)

def init_db():
    # engine = get_engine()
    Base.metadata.create_all(bind=engine)

@contextmanager
def session_scope():
    # SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

# --- Repository helpers (get_or_create / upsert) ---

def get_or_create_role(db, name: str) -> Role:
    obj = db.query(Role).filter_by(name=name).one_or_none()
    if obj: return obj
    obj = Role(name=name)
    try:
        db.add(obj); db.commit()
    except IntegrityError:
        db.rollback()
        obj = db.query(Role).filter_by(name=name).one()
    return obj

def get_or_create_skill(db, name: str, canonical: Optional[str], category: Optional[str]) -> Skill:
    obj = db.query(Skill).filter_by(name=name).one_or_none()
    if obj: return obj
    obj = Skill(name=name, canonical_name=canonical, category=category)
    try:
        db.add(obj); db.commit()
    except IntegrityError:
        db.rollback()
        obj = db.query(Skill).filter_by(name=name).one()
    return obj

def add_alias(db, skill_id: int, alias: str):
    try:
        db.add(SkillAlias(skill_id=skill_id, alias=alias))
        db.commit()
    except IntegrityError:
        db.rollback()

def upsert_role_skill(db, role_id: int, skill_id: int, weight: float):
    rs = db.query(RoleSkill).filter_by(role_id=role_id, skill_id=skill_id).one_or_none()
    if rs:
        rs.weight = weight
    else:
        db.add(RoleSkill(role_id=role_id, skill_id=skill_id, weight=weight))
    db.commit()

def upsert_edge(db, src_skill_id: int, dst_skill_id: int, relation_type: str, weight: float, source: str):
    e = db.query(SkillEdge).filter_by(
        src_skill_id=src_skill_id, dst_skill_id=dst_skill_id, relation_type=relation_type
    ).one_or_none()
    if e:
        e.weight = weight; e.source = source
    else:
        db.add(SkillEdge(src_skill_id=src_skill_id, dst_skill_id=dst_skill_id,
                         relation_type=relation_type, weight=weight, source=source))
    db.commit()

def get_or_create_tool(db, name: str) -> Tool:
    obj = db.query(Tool).filter_by(name=name).one_or_none()
    if obj: return obj
    obj = Tool(name=name)
    try:
        db.add(obj); db.commit()
    except IntegrityError:
        db.rollback()
        obj = db.query(Tool).filter_by(name=name).one()
    return obj

def upsert_skill_tool(db, skill_id: int, tool_id: int, relation_type: str, weight: float, source: str):
    st = db.query(SkillTool).filter_by(skill_id=skill_id, tool_id=tool_id, relation_type=relation_type).one_or_none()
    if st:
        st.weight = weight; st.source = source
    else:
        db.add(SkillTool(skill_id=skill_id, tool_id=tool_id,
                         relation_type=relation_type, weight=weight, source=source))
    db.commit()
    
    
class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)   # 'stackoverflow', etc.
    external_id: Mapped[str] = mapped_column(String(128))         # provider id
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # JSON string of tags
    companies_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    question_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    difficulty: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at_source: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    score: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    hash: Mapped[str] = mapped_column(String(64), index=True)                   # sha256 of canonical text
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_extid"),
                      UniqueConstraint("source", "hash", name="uq_source_hash"))

class Answer(Base):
    __tablename__ = "answers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    body_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at_source: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class QuestionSkill(Base):
    __tablename__ = "question_skills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    __table_args__ = (UniqueConstraint("question_id","skill_id", name="uq_q_skill"),)

# ---------- helpers ----------
def canonical_question_text(title: str, body_md: str | None) -> str:
    t = (title or "").strip().lower()
    b = (body_md or "").strip().lower()
    return f"{t}\n\n{b}"

def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def upsert_question_with_answers(db, item) -> Question:
    """Idempotent upsert based on (source, external_id) or (source, hash)."""
    from json import dumps
    from sqlalchemy import select

    h = getattr(item, "hash", None) or sha256_hex(canonical_question_text(item.title, item.body_markdown))
    # Optional: avoid failing if item is immutable
    try:
        item.hash = h
    except Exception:
        pass

    q = db.execute(
        select(Question).where(
            (Question.source == item.source) &
            ((Question.external_id == item.external_id) | (Question.hash == h))
        )
    ).scalar_one_or_none()

    if q is None:
        q = Question(
            source=item.source,
            external_id=item.external_id,
            url=item.url,
            title=item.title,
            body_markdown=item.body_markdown,
            body_html=item.body_html,
            tags_json=dumps(item.tags),
            companies_json=dumps(item.companies),
            question_type=item.question_type,
            difficulty=item.difficulty,
            created_at_source=item.created_at,
            score=item.score or 0,
            hash=h,
        )
        db.add(q); db.flush()
    else:
        # update minimal fields; keep hash stable
        q.url = item.url
        q.title = item.title
        q.body_markdown = item.body_markdown
        q.body_html = item.body_html
        q.tags_json = dumps(item.tags)
        q.companies_json = dumps(item.companies)
        q.question_type = item.question_type
        q.difficulty = item.difficulty
        q.created_at_source = item.created_at
        q.score = item.score or 0

    # answers
    if item.answers:
        from sqlalchemy import select
        for a in item.answers:
            exists = db.execute(
                select(Answer).where(
                    (Answer.question_id == q.id) & (Answer.external_id == a.external_id)
                )
            ).scalar_one_or_none()
            if exists:  # update
                exists.body_markdown = a.body_markdown
                exists.body_html = a.body_html
                exists.score = a.score or 0
                exists.is_accepted = bool(a.is_accepted)
                exists.created_at_source = a.created_at
            else:
                db.add(Answer(
                    question_id=q.id,
                    external_id=a.external_id,
                    body_markdown=a.body_markdown,
                    body_html=a.body_html,
                    score=a.score or 0,
                    is_accepted=bool(a.is_accepted),
                    created_at_source=a.created_at
                ))

    db.commit()
    return q


# --- Embeddings table for questions (store as JSON for portability) ---
class QuestionVector(Base):
    __tablename__ = "question_vectors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), unique=True, index=True)
    dim: Mapped[int] = mapped_column(Integer)
    embedding_json: Mapped[str] = mapped_column(Text)           # json.dumps(list[float])
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# --- LLM metadata per question ---
class QuestionMeta(Base):
    __tablename__ = "question_meta"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), unique=True, index=True)
    qtype: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)      # Behavioral/Technical/Coding/System Design
    difficulty: Mapped[Optional[str]] = mapped_column(String(16), nullable=True) # Easy/Medium/Hard
    rubric_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # JSON string
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def get_questions_with_any_tags(db, tags: list[str], limit: int = 500):
    """Simple Python-side filter; tags_json is a JSON-encoded list."""
    if not tags:
        return []
    rows = db.execute(select(Question.id, Question.title, Question.body_markdown, Question.url, Question.tags_json)
                      .order_by(Question.score.desc(), Question.id.desc())
                      .limit(limit)).all()
    out = []
    tagset = {t.lower() for t in tags}
    for qid, title, body_md, url, tags_json in rows:
        try:
            qtags = {t.lower() for t in json.loads(tags_json or "[]")}
        except Exception:
            qtags = set()
        if qtags & tagset:
            out.append({"id": qid, "title": title or "", "body_md": body_md or "", "url": url, "tags": list(qtags)})
    return out

def get_or_none_question_vector(db, question_id: int) -> Optional[QuestionVector]:
    return db.query(QuestionVector).filter_by(question_id=question_id).one_or_none()

def upsert_question_vector(db, question_id: int, emb: list[float]):
    qv = db.query(QuestionVector).filter_by(question_id=question_id).one_or_none()
    if qv:
        qv.embedding_json = json.dumps(emb); qv.dim = len(emb)
    else:
        qv = QuestionVector(question_id=question_id, dim=len(emb), embedding_json=json.dumps(emb))
        db.add(qv)
    db.commit()
    return qv

def get_or_none_question_meta(db, question_id: int) -> Optional[QuestionMeta]:
    return db.query(QuestionMeta).filter_by(question_id=question_id).one_or_none()

def upsert_question_meta(db, question_id: int, qtype: str, difficulty: str, rubric: dict):
    jm = json.dumps(rubric, ensure_ascii=False)
    qm = db.query(QuestionMeta).filter_by(question_id=question_id).one_or_none()
    if qm:
        qm.qtype, qm.difficulty, qm.rubric_json = qtype, difficulty, jm
    else:
        qm = QuestionMeta(question_id=question_id, qtype=qtype, difficulty=difficulty, rubric_json=jm)
        db.add(qm)
    db.commit()
    return qm


