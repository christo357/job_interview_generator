from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class AnswerItem(BaseModel):
    external_id: str
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    score: Optional[int] = 0
    is_accepted: Optional[bool] = False
    created_at: Optional[datetime] = None

class QuestionItem(BaseModel):
    source: str = Field(..., description="e.g., 'stackoverflow', 'leetcode', 'glassdoor'")
    external_id: str
    url: str
    title: str
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    companies: List[str] = Field(default_factory=list)  # often empty except Glassdoor/company lists
    question_type: Optional[str] = None  # e.g., 'coding','system-design','behavioral','technical'
    difficulty: Optional[str] = None     # 'Easy','Medium','Hard' (if available)
    created_at: Optional[datetime] = None
    score: Optional[int] = 0
    answers: List[AnswerItem] = Field(default_factory=list)
    # enrichment (later):
    skills: List[str] = Field(default_factory=list)
    skill_scores: dict = Field(default_factory=dict)   # {skill: weight}
    hash: Optional[str] = None