import json
import gradio as gr

from modules.jd_parser import parse_jd
from src.jd2interview.generation.question_generator import generate_questions

# --- Helpers (UI-side filtering) ---
QUESTION_TYPES = ["All", "Behavioral", "Technical", "Coding", "System Design"]
DIFFICULTIES = ["All", "Easy", "Medium", "Hard"]

def read_text_file(file_path: str) -> str:
    if not file_path:
        return ""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def on_parse_click(file_path):
    """Read uploaded JD, parse it, return parsed JSON and store in state."""
    if not file_path:
        return gr.update(value={"error": "No file uploaded"}), None

    jd_text = read_text_file(file_path)
    parsed = parse_jd(jd_text)
    print("\n[Console] Parsed JD:")
    print(json.dumps(parsed, indent=2, ensure_ascii=False))
    return parsed, parsed  # (show in JSON, store in state)

def on_generate_click(parsed_state):
    """Generate mock questions from parsed JD."""
    if not parsed_state:
        return gr.update(value=[{"error": "Parse a JD first"}]), None

    questions = generate_questions(parsed_state)
    print("\n[Console] Generated Questions:")
    for q in questions:
        print(f"- {q['question']} ({q['type']}, {q['difficulty']})")
    return questions, questions  # (show list, store in state)

def on_filter_change(questions_state, qtype, diff):
    """Filter questions using type/difficulty dropdowns."""
    if not questions_state:
        return []
    filtered = []
    for q in questions_state:
        ok_type = (qtype == "All") or (q.get("type") == qtype)
        ok_diff = (diff == "All") or (q.get("difficulty") == diff)
        if ok_type and ok_diff:
            filtered.append(q)
    return filtered

with gr.Blocks(title="JD → Interview Package (Mock)") as demo:
    gr.Markdown("# JD → Interview Package (Mock)\nUpload a JD, parse it, generate questions, and filter them.")

    with gr.Row():
        file_in = gr.File(label="Upload JD (.txt)", file_types=[".txt"], type="filepath")
        parse_btn = gr.Button("Parse JD", variant="primary")

    parsed_json = gr.JSON(label="Parsed JD (mock)")
    parsed_state = gr.State(value=None)

    gr.Markdown("---")
    with gr.Row():
        gen_btn = gr.Button("Generate Questions", variant="secondary")

    with gr.Row():
        qtype_dd = gr.Dropdown(choices=QUESTION_TYPES, value="All", label="Filter: Question Type")
        diff_dd = gr.Dropdown(choices=DIFFICULTIES, value="All", label="Filter: Difficulty")

    questions_json = gr.JSON(label="Generated Questions (with metadata)")
    questions_state = gr.State(value=None)

    # Wire events
    parse_btn.click(
        fn=on_parse_click,
        inputs=file_in,
        outputs=[parsed_json, parsed_state],
    )

    gen_btn.click(
        fn=on_generate_click,
        inputs=parsed_state,
        outputs=[questions_json, questions_state],
    )

    qtype_dd.change(
        fn=on_filter_change,
        inputs=[questions_state, qtype_dd, diff_dd],
        outputs=questions_json,
    )
    diff_dd.change(
        fn=on_filter_change,
        inputs=[questions_state, qtype_dd, diff_dd],
        outputs=questions_json,
    )

if __name__ == "__main__":
    demo.launch()