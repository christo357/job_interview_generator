import json
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from jd2interview.utils.config import settings
from jd2interview.skills.models import SkillGraph, Category, Relation

PROMPT = ChatPromptTemplate.from_template(
"""You are building a compact skill graph for interview design.
Given a parsed JD and its raw text, output a JSON SkillGraph capturing key skills and relations.

Rules:
- 10–30 skill nodes max.
- Use canonical names (e.g., "PostgreSQL" not "Postgres"; "Kubernetes" not "k8s").
- categories: {categories}
- importance in [0,1] for THIS role; higher = more important.
- level in ["beginner","intermediate","advanced"].
- relations: {relations}
  - 'requires' for prerequisites (Docker -> Kubernetes)
  - 'uses_tool' for tool usage (Python -> PyTest)
  - 'part_of' taxonomy (CNN -> Deep Learning)
  - 'related_to' conceptual linkage
  - 'co_occurs_with' frequent pairing in this JD
- Include 'aliases' for normalization.

Return ONLY the JSON matching SkillGraph.

Parsed JD (JSON):
{parsed_json}

Raw JD: {jd_text}
"""
).partial(
    categories=list(Category.__args__),
    relations=list(Relation.__args__),
)

def _structured_llm():
    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.0,
        timeout=settings.OPENAI_TIMEOUT,
        max_retries=settings.OPENAI_MAX_RETRIES if hasattr(settings, "OPENAI_MAX_RETRIES") else 2,
    )
    # returns a model that outputs a SkillGraph object
    return llm.with_structured_output(SkillGraph)

def infer_skill_graph(parsed: dict, jd_text: str) -> SkillGraph:
    # chain = _get_structured_llm()
    # return chain.invoke({"parsed_json": parsed, "jd_text": jd_text})
        # Compose: Prompt → Structured LLM
    chain = PROMPT | _structured_llm()
    # Optional: pretty JSON for readability in the prompt
    parsed_json_str = json.dumps(parsed, ensure_ascii=False, indent=2)
    return chain.invoke({"parsed_json": parsed_json_str, "jd_text": jd_text})