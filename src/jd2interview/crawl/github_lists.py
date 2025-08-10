import base64, requests
from typing import Iterable
from jd2interview.ingest.models import QuestionItem

GH = "https://api.github.com"

def fetch_github_file(owner: str, repo: str, path: str) -> str:
    r = requests.get(f"{GH}/repos/{owner}/{repo}/contents/{path}", timeout=30)
    r.raise_for_status()
    content = r.json()["content"]
    return base64.b64decode(content).decode("utf-8", errors="ignore")

def parse_markdown_questions(md: str) -> Iterable[str]:
    for line in md.splitlines():
        line = line.strip(" -*#\t")
        if len(line) > 15 and line.endswith("?"):
            yield line

def fetch_github_questions(owner, repo, path, source_label) -> Iterable[QuestionItem]:
    md = fetch_github_file(owner, repo, path)
    for q in parse_markdown_questions(md):
        yield QuestionItem(
            source=source_label,
            external_id=f"{owner}/{repo}/{path}:{hash(q)}",
            url=f"https://github.com/{owner}/{repo}/blob/main/{path}",
            title=q[:120],
            body_markdown=q,
            tags=[],
            companies=[],
            question_type=None,
            difficulty=None,
            answers=[],
        )