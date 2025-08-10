from typing import List, Literal, Optional
from pydantic import BaseModel, Field, confloat
from decimal import Decimal

Category = Literal[
    "language","framework","library","cloud","db","orchestration","tool",
    "ml","data","devops","testing","security","soft","domain","other"
]
Level = Literal["beginner","intermediate","advanced"]
Relation = Literal["requires","related_to","part_of","co_occurs_with","uses_tool"]

class SkillNode(BaseModel):
    name: str = Field(..., description="Canonical skill name, e.g., 'Python', 'Kubernetes'")
    category: Category = "other"
    aliases: List[str] = Field(default_factory=list)
    importance: Decimal = Field(0.5, ge=0, le=1)
    level: Level = "intermediate"

class Edge(BaseModel):
    source: str
    target: str
    relation: Relation
    weight: Decimal = Field(0.5, ge=0, le=1)

class SkillGraph(BaseModel):
    role_title: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    skills: List[SkillNode] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)