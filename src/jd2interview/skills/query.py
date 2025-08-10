# src/jd2interview/skills/query.py
from __future__ import annotations
from typing import Dict, List
from sqlalchemy import select, desc, or_

from jd2interview.storage.db import SessionLocal, Role, Skill, RoleSkill, SkillEdge
from typing import List, Tuple
from sqlalchemy import select
from jd2interview.storage.db import SessionLocal, Role, RoleSkill, Skill, SkillEdge

def top_k_skills_for_role(role_id: int, k: int = 5) -> List[Tuple[str, float]]:
    with SessionLocal() as db:
        stmt = (
            select(Skill.name, RoleSkill.weight)
            .join(RoleSkill, RoleSkill.skill_id == Skill.id)
            .where(RoleSkill.role_id == role_id)
            .order_by(RoleSkill.weight.desc(), Skill.name.asc())
            .limit(k)
        )
        return [(n, float(w)) for (n, w) in db.execute(stmt).all()]

def neighbors(skill_name: str, relation_type: str = "related_to") -> List[str]:
    with SessionLocal() as db:
        # get id
        sid = db.query(Skill).filter(Skill.name == skill_name).with_entities(Skill.id).scalar()
        if not sid:
            return []
        q = (
            select(Skill.name)
            .join(SkillEdge, SkillEdge.dst_skill_id == Skill.id)
            .where(SkillEdge.src_skill_id == sid, SkillEdge.relation_type == relation_type)
            .order_by(SkillEdge.weight.desc(), Skill.name.asc())
        )
        return [row[0] for row in db.execute(q).all()]
    
    


def build_role_skill_graph(role_id: int, top_k: int = 50, include_neighbors: int = 30) -> Dict:
    """
    Returns a dict like:
    {
      "role_title": "Data Scientist",
      "skills": [{"id": 12, "name":"Python","weight":0.92, "category": "lang"}, ...],
      "edges":  [{"src":"Python","dst":"Pandas","relation_type":"related_to","weight":0.7}, ...],
      "tags": ["python","sql","ml"]
    }
    """
    out = {"role_title": f"Role {role_id}", "skills": [], "edges": [], "tags": []}

    with SessionLocal() as db:
        role_name = db.query(Role.name).filter(Role.id == role_id).scalar()
        if role_name:
            out["role_title"] = role_name

        # top-K skills for the role
        q = (
            select(Skill.id, Skill.name, Skill.category, RoleSkill.weight)
            .join(RoleSkill, RoleSkill.skill_id == Skill.id)
            .where(RoleSkill.role_id == role_id)
            .order_by(desc(RoleSkill.weight), Skill.name.asc())
            .limit(int(top_k))
        )
        top_sk = db.execute(q).all()
        if not top_sk:
            return out

        id_to_name = {}
        for sid, sname, cat, w in top_sk:
            out["skills"].append({"id": int(sid), "name": sname, "category": cat, "weight": float(w)})
            id_to_name[int(sid)] = sname
            out["tags"].append(sname)
        out["tags"] = sorted({t.lower() for t in out["tags"]})

        # neighbor edges (only include edges incident to top skills)
        if include_neighbors and include_neighbors > 0:
            top_ids = [int(s["id"]) for s in out["skills"]]
            e = (
                select(SkillEdge.src_skill_id, SkillEdge.dst_skill_id, SkillEdge.relation_type, SkillEdge.weight)
                .where(or_(SkillEdge.src_skill_id.in_(top_ids), SkillEdge.dst_skill_id.in_(top_ids)))
                .order_by(desc(SkillEdge.weight))
                .limit(int(include_neighbors))
            )
            edges = db.execute(e).all()
            # make sure we have names for both ends (query names if necessary)
            missing_ids = {sid for row in edges for sid in (int(row[0]), int(row[1])) if sid not in id_to_name}
            if missing_ids:
                name_rows = db.execute(
                    select(Skill.id, Skill.name).where(Skill.id.in_(list(missing_ids)))
                ).all()
                for sid, sname in name_rows:
                    id_to_name[int(sid)] = sname

            for src_id, dst_id, rtype, w in edges:
                src = id_to_name.get(int(src_id))
                dst = id_to_name.get(int(dst_id))
                if src and dst:
                    out["edges"].append({
                        "src": src, "dst": dst,
                        "relation_type": rtype, "weight": float(w)
                    })
                    
            have = {s["name"] for s in out["skills"]}
            for e in out["edges"]:
                for nm in (e["src"], e["dst"]):
                    if nm not in have:
                        out["skills"].append({"id": None, "name": nm, "category": "neighbor", "weight": 0.1})
                        have.add(nm)

    return out