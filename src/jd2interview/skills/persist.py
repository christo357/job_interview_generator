from typing import Tuple, List
from jd2interview.skills.models import SkillGraph
from jd2interview.storage.db import (
    session_scope, init_db, get_or_create_role, get_or_create_skill, add_alias,
    upsert_role_skill, upsert_edge, get_or_create_tool, upsert_skill_tool
)

def persist_skill_graph(graph: SkillGraph) -> Tuple[int, List[Tuple[str, float]]]:
    """Writes a SkillGraph into DB and returns (role_id, ranked skills by importance)."""
    init_db()
    role_title = graph.role_title or "Unknown Role"
    ranked = sorted([(n.name, float(n.importance)) for n in graph.skills],
                    key=lambda kv: kv[1], reverse=True)

    with session_scope() as db:
        role = get_or_create_role(db, role_title)

        # nodes
        name_to_id = {}
        for node in graph.skills:
            sk = get_or_create_skill(db, name=node.name, canonical=node.name, category=node.category)
            name_to_id[node.name] = sk.id
            for a in node.aliases:
                if a and a.strip() and a.strip().lower() != node.name.lower():
                    add_alias(db, sk.id, a.strip())
            upsert_role_skill(db, role.id, sk.id, float(node.importance))

        # edges
        for e in graph.edges:
            src_id = name_to_id.get(e.source)
            dst_id = name_to_id.get(e.target)
            if e.relation == "uses_tool":
                if src_id and dst_id:
                    upsert_edge(db, src_id, dst_id, "uses_tool", float(e.weight), "llm")
                elif src_id and not dst_id:
                    tool = get_or_create_tool(db, e.target)
                    upsert_skill_tool(db, src_id, tool.id, "uses_tool", float(e.weight), "llm")
            else:
                if src_id and dst_id and src_id != dst_id:
                    upsert_edge(db, src_id, dst_id, e.relation, float(e.weight), "llm")

        return role.id, ranked