# modules/question_generator.py
from typing import Dict, List

BASE_QUESTIONS = [
    {
        "question": "Tell me about a challenging project you led and how you managed it.",
        "type": "Behavioral",
        "difficulty": "Easy",
        "rubric": "Leadership, ownership, communication, measurable impact."
    },
    {
        "question": "How would you optimize a database query that is running slow?",
        "type": "Technical",
        "difficulty": "Medium",
        "rubric": "Indexing, query plans, caching, schema changes, measurement."
    },
    {
        "question": "Write a function to reverse a linked list and state its time complexity.",
        "type": "Coding",
        "difficulty": "Hard",
        "rubric": "Pointer manipulation, O(n) time, O(1) space, edge cases."
    },
    {
        "question": "Design a high-level architecture for a service that ingests CSVs and provides a REST API for queries.",
        "type": "System Design",
        "difficulty": "Medium",
        "rubric": "Ingestion, storage, indexing, API, scalability, reliability."
    }
]

SKILL_TO_QUESTION = {
    "Python": {
        "question": "Explain how you'd structure a Python package for a data pipeline project.",
        "type": "Technical",
        "difficulty": "Medium",
        "rubric": "Modules, packaging, dependency management, testing, CLI."
    },
    "SQL": {
        "question": "Given a large table with slow aggregations, how would you improve performance?",
        "type": "Technical",
        "difficulty": "Medium",
        "rubric": "Indexes, partitions, materialized views, query rewrites."
    },
    "AWS": {
        "question": "Design a cost-effective, highly-available web API on AWS.",
        "type": "System Design",
        "difficulty": "Medium",
        "rubric": "ALB, ASG/Lambda, RDS/DynamoDB, S3, caching, cost tradeoffs."
    },
    "Docker": {
        "question": "What best practices do you follow when writing Dockerfiles for Python apps?",
        "type": "Technical",
        "difficulty": "Easy",
        "rubric": "Multi-stage builds, minimal base, caching, non-root, reproducibility."
    },
    "Kubernetes": {
        "question": "How do you roll out a zero-downtime deployment on Kubernetes?",
        "type": "Technical",
        "difficulty": "Hard",
        "rubric": "Readiness probes, rolling updates, HPA, canary/blue-green."
    }
}

def generate_questions(parsed_info: Dict) -> List[Dict]:
    """
    Mock question generator. Uses parsed skills to add a few tailored questions.
    Replace with LangChain/OpenAI later.
    """
    questions = BASE_QUESTIONS.copy()

    skills = parsed_info.get("skills", []) if parsed_info else []
    for s in skills:
        if s in SKILL_TO_QUESTION:
            questions.append(SKILL_TO_QUESTION[s])

    # Deduplicate by question text
    seen = set()
    uniq = []
    for q in questions:
        if q["question"] not in seen:
            uniq.append(q)
            seen.add(q["question"])

    # Add mock bank-match tag (placeholder for vector search)
    for q in uniq:
        q["bank_match"] = {"matched": False, "id": None, "score": None}

    return uniq