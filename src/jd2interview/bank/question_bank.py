# modules/question_bank.py
# Placeholder for a central bank + matching (vector search, tags, etc.)

MOCK_BANK = [
    {
        "id": "q-101",
        "question": "Tell me about a challenging project you led and how you managed it.",
        "tags": ["Behavioral", "Leadership"]
    },
    {
        "id": "q-202",
        "question": "Write a function to reverse a linked list and state its time complexity.",
        "tags": ["Coding", "DSA"]
    }
]

def mock_match_to_bank(question_text: str):
    """Naive exact-match stub. Replace with embeddings + FAISS/Pinecone."""
    for item in MOCK_BANK:
        if item["question"].strip().lower() == question_text.strip().lower():
            return {"matched": True, "id": item["id"], "score": 1.0}
    return {"matched": False, "id": None, "score": 0.0}