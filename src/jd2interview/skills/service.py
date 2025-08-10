from typing import Tuple, List, Dict, Any
from jd2interview.skills.llm_graph import infer_skill_graph
from jd2interview.skills.persist import persist_skill_graph
from jd2interview.skills.models import SkillGraph

def build_and_store_skill_graph(parsed: Dict[str, Any], jd_text: str) -> Tuple[int, SkillGraph, List[tuple]]:
    """
    End-to-end: LLM → SkillGraph → DB. Returns (role_id, graph, ranked_top).
    """
    graph = infer_skill_graph(parsed, jd_text)     # structured LLM output
    role_id, ranked = persist_skill_graph(graph)   # transactional persistence
    return role_id, graph, ranked