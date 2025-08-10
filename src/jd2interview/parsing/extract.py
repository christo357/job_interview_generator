import json
import os
import re
from pathlib import Path
from typing import Dict, Iterable, Tuple

from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from jd2interview.utils.config import settings

# Prompt (doubling braces to show literal JSON braces)
PROMPT = ChatPromptTemplate.from_template("""
You are an assistant that extracts structured fields from a job description.
Given the text of the complete job description, output a JSON object with keys:
{{
  "job_title": "",
  "skills": [],
  "tools": [],
  "responsibilities": [],
  "experience": []
}}

Input Job Description:
```{jd_text}```

Respond with only the JSON object — no markdown, no backticks, no commentary.
""")

# IMPORTANT: use model= and api_key= on modern langchain_openai
llm = ChatOpenAI(
    model=getattr(settings, "OPENAI_MODEL", "gpt-5-mini"),  # Fixed model name
    temperature=0.0,
    api_key= getattr(settings, "OPENAI_API_KEY", None),
)
# Runnable pipeline - this is correct
chain = PROMPT | llm | StrOutputParser()

def _coerce_json(text: str) -> Dict:
    t = text.strip()
    # Strip code fences if model ignored instructions
    t = re.sub(r"^```json\s*|\s*```$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^```\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # Try extracting the outermost JSON object
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            return json.loads(t[start:end+1])
        raise

def extract_structured(jd_text: str) -> Dict:
    try:
        raw_text = chain.invoke({"jd_text": jd_text})  # returns a string
    except Exception as e:
        # Surface the real error (API key, model access, network, etc.)
        raise RuntimeError(f"LLM call failed: {type(e).__name__}: {e}") from e

    try:
        obj = _coerce_json(raw_text)
    except Exception as e:
        raise ValueError(f"Failed to parse JSON from LLM response.\n--- RAW ---\n{raw_text}\n--- ERR ---\n{e}") from e

    # Validate and normalize the response structure
    required_keys = ["job_title", "skills", "tools", "responsibilities", "experience"]
    for key in required_keys:
        if key not in obj:
            raise ValueError(f"LLM response missing required key: {key}")

    return {
        "job_title": str(obj.get("job_title", "") or ""),
        "skills": list(obj.get("skills", []) or []),
        "tools": list(obj.get("tools", []) or []),
        "responsibilities": list(obj.get("responsibilities", []) or []),
        "experience": list(obj.get("experience", []) or []),
    }


# Optional: bulk loader if you still want it
def load_processed_jds(processed_dir: str = "data/processed"):
    for fn in os.listdir(processed_dir):
        if fn.endswith(".txt"):
            job_id = os.path.splitext(fn)[0]
            with open(os.path.join(processed_dir, fn), "r", encoding="utf-8") as f:
                yield job_id, f.read()

if __name__ == "__main__":
    # Quick smoke test to check your key/model
    sample = "Title: Software Engineer\nRequirements: Python, SQL, AWS\nExperience: 3+ years"
    print(extract_structured(sample))