# src/jd2interview/ui/gradio_app.py
from __future__ import annotations
import json
from pathlib import Path
from typing import List, Dict, Optional
from collections import Counter

import gradio as gr
from sqlalchemy import select, desc
import markdown as _md
import bleach
from html import escape as _esc

from jd2interview.utils.config import settings
from jd2interview.storage.db import (
    init_db, SessionLocal, Question, QuestionMeta, Answer
)
from jd2interview.parsing.extract import extract_structured
from jd2interview.skills.service import build_and_store_skill_graph
from jd2interview.crawl.role_aware import crawl_for_role_stream
from jd2interview.enrich.metadata import classify_role_questions_stream
from jd2interview.retrieval.availability import fetch_typed_questions_for_role
from jd2interview.generation.llm_qna import generate_qna_for_role
from jd2interview.skills.viz import  graph_html_iframe
from jd2interview.skills.query import build_role_skill_graph

QUESTION_TYPES = ["All", "Behavioral", "Technical", "Coding", "System Design"]
DIFFICULTIES   = ["All", "Easy", "Medium", "Hard"]
SOURCE_CHOICES = ["Web only", "LLM only", "Web + LLM"]

_ALLOWED_TAGS = bleach.sanitizer.ALLOWED_TAGS.union({
    "p","pre","code","blockquote","hr","br",
    "h1","h2","h3","h4","h5","h6","ul","ol","li",
    "table","thead","tbody","tr","th","td","em","strong","a","span","div"
})
_ALLOWED_ATTRS = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "a": ["href","title","target","rel"],
    "span": ["class"],
    "div": ["class"],
    "code": ["class"],
    "pre": ["class"],
}

# ---------- helpers ----------
def read_text_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def _sources_for_mode(mode: str):
    if mode == "Web only":
        return ["stackexchange"]
    if mode == "LLM only":
        return ["generated"]
    return None  # both

def _fetch_all_typed_questions(
    qtype: Optional[str] = None,
    sources: Optional[List[str]] = None,
    limit: int = 10000,
) -> List[Dict]:
    out: List[Dict] = []
    with SessionLocal() as db:
        q = (
            select(Question, QuestionMeta)
            .join(QuestionMeta, QuestionMeta.question_id == Question.id)
            .order_by(Question.score.desc(), Question.id.desc())
            .limit(limit)
        )
        for Q, M in db.execute(q).all():
            if qtype and M.qtype != qtype:
                continue
            if sources and Q.source not in sources:
                continue
            try:
                rubric = json.loads(M.rubric_json or "{}")
            except Exception:
                rubric = {}
            try:
                tags = json.loads(Q.tags_json or "[]")
            except Exception:
                tags = []
            ans = db.execute(
                select(Answer.body_markdown)
                .where(Answer.question_id == Q.id)
                .order_by(desc(Answer.is_accepted), desc(Answer.score))
                .limit(1)
            ).scalar_one_or_none()
            out.append({
                "id": Q.id,
                "question": (Q.title or "") + (
                    "\n\n" + (Q.body_markdown or Q.body_html or "")
                    if (Q.body_markdown or Q.body_html) else ""
                ),
                "type": M.qtype,
                "difficulty": M.difficulty,
                "evaluation_rubric": rubric,
                "url": Q.url,
                "tags": tags,
                "source": Q.source,
                "answer": ans or "",
            })
    return out

def _current_items_for_view(state, source_mode, qtype, diff):
    sources = _sources_for_mode(source_mode)
    if state and state.get("role_id"):
        role_id = int(state["role_id"])
        if sources == ["generated"]:  # LLM only → show global generated (not role-filtered)
            items = _fetch_all_typed_questions(qtype=None, sources=sources)
        else:
            items = fetch_typed_questions_for_role(role_id=role_id, qtype=None, sources=sources)
    else:
        items = _fetch_all_typed_questions(qtype=None, sources=sources)

    if qtype != "All":
        items = [q for q in items if q.get("type") == qtype]
    if diff != "All":
        items = [q for q in items if q.get("difficulty") == diff]
    return items

def _counts_label(state, source_mode: str, difficulty: str = "All") -> str:
    try:
        items = _current_items_for_view(state, source_mode, qtype="All", diff=difficulty)
        c = Counter((q.get("type") or "Unknown") for q in items)
        total = len(items)
        beh = c.get("Behavioral", 0)
        tech = c.get("Technical", 0)
        code = c.get("Coding", 0)
        sysd = c.get("System Design", 0)
        parts = [
            f"All ({total})",
            f"Technical ({tech})",
            f"Coding ({code})",
            f"System Design ({sysd})",
            f"Behavioral ({beh})",
        ]
        unk = c.get("Unknown", 0)
        if unk:
            parts.append(f"Unknown ({unk})")
        return "**Available:** " + " • ".join(parts)
    except Exception as e:
        return f"_Counts unavailable: {e}_"

def _current_count_md(items) -> str:
    return f"**Currently showing:** {len(items or [])}"

def _md_to_html(text: str) -> str:
    html = _md.markdown(text or "", extensions=["fenced_code", "tables", "codehilite"])
    return bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)

def on_show_skill_graph(state, top_k, neighbors):
    if not isinstance(state, dict) or not state.get("role_id"):
        return "<em>Parse a JD first.</em>", {}
    role_id = int(state["role_id"])
    try:
        g = build_role_skill_graph(role_id, top_k=int(top_k or 50), include_neighbors=int(neighbors or 30))
        html = graph_html_iframe(g)      # <— use iframe renderer
        return html, g
    except Exception as e:
        return f"<em>Failed to render graph: {e}</em>", {}

def _render_questions_html(items) -> str:
    if not items:
        return "<em>No questions match the current filters.</em>"
    css = """
    <style>
    .qcard{margin:12px 0;border:1px solid #333;border-radius:12px;padding:12px;background:#0f1115}
    .qhead{display:flex;justify-content:space-between;align-items:center}
    .qtitle{font-weight:600;font-size:15px}
    .qdom{font-size:12px;opacity:.85}
    .tags{margin-top:6px}
    .tag{display:inline-block;padding:2px 8px;margin:2px;border-radius:999px;border:1px solid #444;font-size:12px}
    details{margin-top:8px}
    summary{cursor:pointer;opacity:.9}
    .meta dt{font-weight:600}
    .meta dd{margin:0 0 6px 0}
    </style>
    """
    parts = [css]
    for i, q in enumerate(items, 1):
        question_md = q.get("question") or ""
        title_line = question_md.split("\n", 1)[0].strip()
        tags = q.get("tags") or []
        domains = " • ".join(str(t) for t in tags) if tags else "—"

        body_rest_md = ""
        if "\n" in question_md:
            body_rest_md = question_md.split("\n", 1)[1].strip()
        body_html = _md_to_html(body_rest_md) if body_rest_md else ""

        ans_md = q.get("answer") or ""
        ans_html = _md_to_html(ans_md) if ans_md else ""

        rubric = q.get("evaluation_rubric") or {}
        meta_obj = {
            "type": q.get("type"),
            "difficulty": q.get("difficulty"),
            "evaluation_rubric": rubric,
        }
        meta_json = json.dumps(meta_obj, indent=2, ensure_ascii=False)

        parts.append('<div class="qcard">')
        parts.append(f'<div class="qhead"><div class="qtitle">{i}. {title_line}</div><div class="qdom">{domains}</div></div>')
        if body_html:
            parts.append(f'<details><summary>Full text</summary>{body_html}</details>')
        if ans_html:
            parts.append(f'<details><summary>Answer</summary>{ans_html}</details>')
        parts.append(
            f'<details><summary>Metadata</summary>'
            f'<dl class="meta">'
            f'<dt>Type</dt><dd>{q.get("type","")}</dd>'
            f'<dt>Difficulty</dt><dd>{q.get("difficulty","")}</dd>'
            f'<dt>Evaluation rubric</dt>'
            f'<dd><pre><code>{bleach.clean(meta_json)}</code></pre></dd>'
            f'</dl></details>'
        )
        parts.append('</div>')
    return "\n".join(parts)

def _render_parsed_html(preview: dict) -> str:
    if not preview or "parsed" not in preview:
        return "<em>No parsed JD yet.</em>"
    p = preview.get("parsed", {})
    role = _esc(preview.get("skill_graph_preview", {}).get("role_title", p.get("job_title", "Role")))
    skills = p.get("skills") or []
    tools  = p.get("tools") or []
    resp   = p.get("responsibilities") or []
    exp    = p.get("experience") or []

    def _ul(xs):
        xs = [x for x in xs if x]
        if not xs: return "<em>-</em>"
        return "<ul>" + "".join([f"<li>{_esc(str(x))}</li>" for x in xs]) + "</ul>"

    return f"""
        <style>
        .card{{border:1px solid #333;border-radius:10px;padding:12px;background:#111}}
        .card h3{{margin:0 0 8px 0}}
        .section h4{{margin:10px 0 6px 0}}
        </style>
        <div class="card">
        <h3>{role}</h3>
        <div class="section"><h4>Skills</h4>{_ul(skills)}</div>
        <div class="section"><h4>Tools</h4>{_ul(tools)}</div>
        <div class="section"><h4>Responsibilities</h4>{_ul(resp)}</div>
        <div class="section"><h4>Experience</h4>{_ul(exp)}</div>
        </div>
    """

# ---------- parsing core & events ----------
def parse_core(jd_text: str, source_mode: str, qtype: str, diff: str):
    if not (jd_text or "").strip():
        return "<em>No JD text provided.</em>", None, "<em>No items</em>", "_", "_", "JD"

    try:
        init_db()
        parsed = extract_structured(jd_text)
        role_id, graph, ranked = build_and_store_skill_graph(parsed, jd_text)
    except Exception as e:
        return f"<em>Parse/graph failed: {type(e).__name__}: {e}</em>", None, "<em>No items</em>", "_", "_", "JD"

    role_title = getattr(graph, "role_title", None) or parsed.get("job_title", "Role")
    preview = {
        "parsed": parsed,
        "skill_graph_preview": {
            "role_title": role_title,
            "top_skills": (ranked or [])[:10],
            "tags": getattr(graph, "tags", []) or [],
            "n_nodes": len(getattr(graph, "skills", []) or []),
            "n_edges": len(getattr(graph, "edges", []) or []),
        }
    }
    state = {"job_id": "typed", "parsed": parsed, "jd_text": jd_text, "role_id": role_id, "role_title": role_title}

    items  = _current_items_for_view(state, source_mode, qtype, diff)
    counts = _counts_label(state, source_mode, diff)
    shown  = _current_count_md(items)

    # Switch view to Questions by setting nav_mode
    return _render_parsed_html(preview), state, _render_questions_html(items), counts, shown, "Questions"

def on_parse_file_click(file_obj, source_mode, qtype, diff):
    if not file_obj:
        return "<em>No file uploaded.</em>", None, "<em>No items</em>", "_", "_", "JD"
    file_path = file_obj.name if hasattr(file_obj, "name") else file_obj
    try:
        jd_text = read_text_file(file_path)
    except Exception as e:
        return f"<em>Failed to read file: {e}</em>", None, "<em>No items</em>", "_", "_", "JD"
    return parse_core(jd_text, source_mode, qtype, diff)

def on_parse_text_click(jd_text, source_mode, qtype, diff):
    return parse_core(jd_text, source_mode, qtype, diff)

# ---------- generate & refresh ----------
# def on_generate_questions(state, source_mode, diff):
#     if not state or not state.get("role_id"):
#         yield {"status": "Parse a JD first to scope results to the job."}
#         return
#     role_id = int(state["role_id"])

#     if source_mode in ("Web only", "Web + LLM"):
#         for msg in crawl_for_role_stream(role_id):
#             yield {"status": f"[crawl] {msg}"}
#         for msg in classify_role_questions_stream(role_id, batch_size=25, max_items=None):
#             yield {"status": f"[classify] {msg}"}

#     if source_mode in ("LLM only", "Web + LLM"):
#         counts = getattr(settings, "LLM_GEN_COUNTS", None) or {"Technical": 6, "Coding": 6, "Behavioral": 4}
#         restrict = diff if diff in {"Easy","Medium","Hard"} else ""
#         total = 0
#         for typ, cnt in counts.items():
#             c = int(cnt or 0)
#             if c <= 0: 
#                 continue
#             _ = generate_qna_for_role(
#                 role_id, target_type=typ, count=c,
#                 difficulty_policy="Mixed (let the model balance)",
#                 code_lang="Python",
#                 persist=True,
#                 restrict_difficulty=restrict
#             )
#             total += c
#         yield {"status": f"[llm] Generated ~{total} (restrict={restrict or 'None'})"}

#     yield {"status": "Done"}

def on_generate_questions(state, source_mode):
    if not state or not state.get("role_id"):
        yield {"status": "Parse a JD first to scope results to the job."}
        return

    role_id = int(state["role_id"])

    if source_mode in ("Web only", "Web + LLM"):
        # crawl (role-aware) → classify
        for msg in crawl_for_role_stream(role_id):
            yield {"status": f"[crawl] {msg}"}
        for msg in classify_role_questions_stream(role_id, batch_size=25, max_items=None):
            yield {"status": f"[classify] {msg}"}

    if source_mode in ("LLM only", "Web + LLM"):
        # generate and persist
        for typ, cnt in settings.LLM_GEN_COUNTS.items():
            if int(cnt) > 0:
                _ = generate_qna_for_role(role_id, target_type=typ, count=int(cnt), persist=True)
        yield {"status": f"[llm] Generated: {settings.LLM_GEN_COUNTS}"}

    yield {"status": "Done"}
    
def _generate_and_refresh(state, source_mode, qtype, diff):
    try:
        for msg in on_generate_questions(state, source_mode):
            yield gr.update(), msg.get("status", ""), "", ""
    except Exception as e:
        yield gr.update(), f"**Error:** {e}", "", ""
    try:
        items  = _current_items_for_view(state, source_mode, qtype, diff)
        html   = _render_questions_html(items)
        counts = _counts_label(state, source_mode, diff)
        shown  = _current_count_md(items)
        yield html, "Refreshed.", counts, shown
    except Exception as e:
        yield f"<em>Failed to refresh: {e}</em>", "Error", "_", "_"

def on_filter_change_with_counts(state, source_mode, qtype, diff):
    try:
        items  = _current_items_for_view(state, source_mode, qtype, diff)
        html   = _render_questions_html(items)
        counts = _counts_label(state, source_mode, diff)
        shown  = _current_count_md(items)
        return html, counts, shown
    except Exception as e:
        return f"<em>Failed to load items: {e}</em>", "_", "**Currently showing:** 0"

def initial_load(source_mode, qtype, diff):
    try:
        items  = _current_items_for_view(None, source_mode, qtype, diff)
        html   = _render_questions_html(items)
        counts = _counts_label(None, source_mode, diff)
        shown  = _current_count_md(items)
        return html, counts, shown
    except Exception as e:
        return f"<em>Failed to load items: {e}</em>", "_", "**Currently showing:** 0"

# ---------- UI ----------
def build_ui():
    init_db()

    with gr.Blocks(title="JD → Questions") as demo:
        gr.Markdown("## JD → Skill Graph → Questions")

        # Global state
        state    = gr.State(value=None)  # dict with role_id, parsed, etc.
        nav_mode = gr.State(value="JD")  # "JD" or "Questions"

        # ------------- small helpers -------------
        def _update_views(mode):
            # toggle JD vs Questions view
            return (
                gr.update(visible=(mode == "JD")),
                gr.update(visible=(mode == "Questions")),
            )

        def _before_parse():
            # show a short status line; Gradio also shows a spinner during .click()
            return gr.update(value="⏳ Parsing JD… building skill graph…")

        def _after_parse():
            return gr.update(value="")

        def on_refresh_view(state, source_mode, qtype, diff):
            try:
                items_html, counts, shown = on_filter_change_with_counts(state, source_mode, qtype, diff)
                return items_html, counts, shown
            except Exception as e:
                return f"<em>Refresh failed: {e}</em>", "_", "_"

        # ---------------- JD ENTRY VIEW ----------------
        jd_group = gr.Group(visible=True)
        with jd_group:
            gr.Markdown("### Paste or upload a Job Description")

            jd_text_in = gr.Textbox(
                label="Paste JD",
                lines=16,
                placeholder="Paste or type the full job description here…",
            )
            file_in = gr.File(label="…or upload JD (.txt)", file_types=[".txt"])

            with gr.Row():
                parse_text_btn   = gr.Button("Parse Text JD", variant="primary")
                parse_file_btn   = gr.Button("Parse File JD")
                go_questions_btn = gr.Button("Go to Questions")

            parse_status = gr.Markdown("")        # shows the small spinner line
            parsed_html  = gr.HTML(label="Parsed JD & Graph Preview")

        # ---------------- QUESTIONS VIEW ----------------
        q_group = gr.Group(visible=False)
        with q_group:
            gr.Markdown("### Generate & Filter Questions")

            with gr.Row():
                source_mode = gr.Radio(
                    choices=["Web only", "LLM only", "Web + LLM"],
                    value="Web only",
                    label="Source"
                )
                qtype_dd = gr.Dropdown(
                    choices=["All", "Behavioral", "Technical", "Coding", "System Design"],
                    value="All",
                    label="Filter: Type",
                )
                diff_dd = gr.Dropdown(
                    choices=["All", "Easy", "Medium", "Hard"],
                    value="All",
                    label="Filter: Difficulty",
                )

            counts_md = gr.Markdown("")            # All(..) • Technical(..) • ...
            shown_md  = gr.Markdown("")            # Currently showing: N

            with gr.Row():
                gen_btn     = gr.Button("Generate questions", variant="primary")
                refresh_btn = gr.Button("Refresh")
                go_jd_btn   = gr.Button("Enter/Change JD")

            status_md      = gr.Markdown("")       # streaming crawl/classify/llm logs
            questions_html = gr.HTML(label="Questions")

            # --- Skill Graph panel ---
            with gr.Accordion("Skill Graph (role)", open=False):
                with gr.Row():
                    topk_in  = gr.Slider(10, 150, value=50, step=5, label="Top-K role skills")
                    nbr_in   = gr.Slider(0, 150, value=30, step=5, label="Neighbors per graph")
                    render_graph_btn = gr.Button("Show / Refresh graph")
                graph_html = gr.HTML(label="Graph")
                graph_json = gr.JSON(label="Graph (nodes & edges)")

        # ---------------- On app load ----------------
        demo.load(_update_views, inputs=nav_mode, outputs=[jd_group, q_group])
        demo.load(initial_load, inputs=[source_mode, qtype_dd, diff_dd],
                  outputs=[questions_html, counts_md, shown_md])

        # ---------------- Parse flows (with spinner + auto-nav + auto-graph) ----------------
        # Text JD
        parse_text_btn.click(
            _before_parse, inputs=None, outputs=[parse_status]
        ).then(
            on_parse_text_click,
            inputs=[jd_text_in, source_mode, qtype_dd, diff_dd],
            outputs=[parsed_html, state, questions_html, counts_md, shown_md, nav_mode],
            queue=True,
        ).then(
            _update_views, inputs=nav_mode, outputs=[jd_group, q_group]
        ).then(
            on_show_skill_graph,
            inputs=[state, topk_in, nbr_in],
            outputs=[graph_html, graph_json],
        ).then(
            _after_parse, inputs=None, outputs=[parse_status]
        )

        # File JD
        parse_file_btn.click(
            _before_parse, inputs=None, outputs=[parse_status]
        ).then(
            on_parse_file_click,
            inputs=[file_in, source_mode, qtype_dd, diff_dd],
            outputs=[parsed_html, state, questions_html, counts_md, shown_md, nav_mode],
            queue=True,
        ).then(
            _update_views, inputs=nav_mode, outputs=[jd_group, q_group]
        ).then(
            on_show_skill_graph,
            inputs=[state, topk_in, nbr_in],
            outputs=[graph_html, graph_json],
        ).then(
            _after_parse, inputs=None, outputs=[parse_status]
        )

        # Manual navigation buttons
        go_questions_btn.click(lambda: "Questions", outputs=nav_mode).then(
            _update_views, inputs=nav_mode, outputs=[jd_group, q_group]
        )
        go_jd_btn.click(lambda: "JD", outputs=nav_mode).then(
            _update_views, inputs=nav_mode, outputs=[jd_group, q_group]
        )

        # ---------------- Filters wiring ----------------
        qtype_dd.change(
            on_filter_change_with_counts,
            inputs=[state, source_mode, qtype_dd, diff_dd],
            outputs=[questions_html, counts_md, shown_md],
        )
        diff_dd.change(
            on_filter_change_with_counts,
            inputs=[state, source_mode, qtype_dd, diff_dd],
            outputs=[questions_html, counts_md, shown_md],
        )
        source_mode.change(
            on_filter_change_with_counts,
            inputs=[state, source_mode, qtype_dd, diff_dd],
            outputs=[questions_html, counts_md, shown_md],
        )

        # ---------------- Generate (streams status; then refresh) ----------------
        gen_btn.click(
            _generate_and_refresh,
            inputs=[state, source_mode, qtype_dd, diff_dd],
            outputs=[questions_html, status_md, counts_md, shown_md],
            queue=True,
        )

        # ---------------- Refresh ----------------
        refresh_btn.click(
            on_refresh_view,
            inputs=[state, source_mode, qtype_dd, diff_dd],
            outputs=[questions_html, counts_md, shown_md],
        )

        # ---------------- Skill graph manual render ----------------
        render_graph_btn.click(
            on_show_skill_graph,
            inputs=[state, topk_in, nbr_in],
            outputs=[graph_html, graph_json],
            queue=True,
        )

    return demo

def main():
    print(f"[cfg] model={settings.OPENAI_MODEL}, key_prefix={str(settings.OPENAI_API_KEY)[:6]}…")
    print(f"[CFG] DB={settings.DB_URL}")
    print(f"[   CFG] StackExchange key present: {bool(getattr(settings, 'STACKEXCHANGE_KEY', ''))}")
    init_db()
    demo = build_ui()
    demo.queue(default_concurrency_limit=2).launch()

if __name__ == "__main__":
    main()