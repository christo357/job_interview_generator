# src/jd2interview/skills/viz.py
from __future__ import annotations
from typing import Dict, Set
import html as _html

def _normalize_graph(gdict: Dict) -> Dict:
    """Ensure neighbor nodes exist for all edge endpoints and give them small weight."""
    skills = list(gdict.get("skills") or [])
    edges  = list(gdict.get("edges") or [])

    by_name = {s.get("name"): s for s in skills if s.get("name")}
    present: Set[str] = set(by_name.keys())

    # Ensure endpoints exist
    for e in edges:
        for nm in (e.get("src"), e.get("dst")):
            if nm and nm not in present:
                by_name[nm] = {"id": None, "name": nm, "category": "neighbor", "weight": 0.1}
                present.add(nm)

    return {"skills": list(by_name.values()), "edges": edges, "role_title": gdict.get("role_title", "Role")}

def graph_html_iframe(gdict: Dict) -> str:
    """
    Returns an <iframe srcdoc="..."> with a vis-network graph.
    No external Python libs required.
    """
    if not gdict:
        return "<em>No graph data.</em>"

    g = _normalize_graph(gdict)
    skills = g["skills"]
    edges  = g["edges"]

    if not skills and not edges:
        return "<em>No skills/edges for this role yet. Parse a JD first.</em>"

    # Build JS arrays
    def js_str(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    nodes_js = []
    for s in skills:
        name = s.get("name") or ""
        w = float(s.get("weight", 1.0) or 1.0)
        label = js_str(name)
        title = js_str(f"{name} (w={w:.2f})")
        size  = 14 + int(24 * max(0.0, min(1.0, (w - 0.0) / max(1.0, w))))  # simple size heuristic
        nodes_js.append(f'{{id:"{label}", label:"{label}", title:"{title}", value:{w:.4f}, font:{{multi:"md"}}, size:{size}}}')

    edges_js = []
    for e in edges:
        src = e.get("src") or ""
        dst = e.get("dst") or ""
        rt  = e.get("relation_type") or ""
        w   = float(e.get("weight", 1.0) or 1.0)
        title = js_str(f"{rt} ({w:.2f})")
        edges_js.append(f'{{from:"{js_str(src)}", to:"{js_str(dst)}", value:{w:.4f}, title:"{title}", arrows:"to"}}')

    nodes_str = "[" + ",".join(nodes_js) + "]"
    edges_str = "[" + ",".join(edges_js) + "]"

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Role Skill Graph</title>
<style>
  html,body {{ background:#0f1115; color:#eaeaea; margin:0; padding:0; }}
  #mynetwork {{ width:100%; height:640px; border:0; background:#0f1115; }}
</style>
<!-- vis-network UMD (CDN) -->
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
</head>
<body>
<div id="mynetwork"></div>
<script>
  const nodes = new vis.DataSet({nodes_str});
  const edges = new vis.DataSet({edges_str});
  const container = document.getElementById('mynetwork');
  const data = {{ nodes, edges }};
  const options = {{
    nodes: {{
      shape: "dot",
      scaling: {{ min: 10, max: 50 }},
    }},
    edges: {{
      smooth: true,
      color: {{ opacity: 0.6 }},
      arrows: "to"
    }},
    physics: {{
      solver: "forceAtlas2Based",
      stabilization: {{ iterations: 200 }}
    }},
    interaction: {{
      hover: true,
      tooltipDelay: 120,
      navigationButtons: true,
      keyboard: true
    }}
  }};
  new vis.Network(container, data, options);
</script>
</body>
</html>"""
    # Escape for srcdoc attribute
    return f'<iframe srcdoc="{_html.escape(html, quote=True)}" style="width:100%;height:660px;border:0;"></iframe>'