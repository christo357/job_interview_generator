# smoke_test.py
import os, sys, traceback
from importlib.metadata import version, PackageNotFoundError

def dist_ver(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "NOT INSTALLED"

print("CWD:", os.getcwd())
print("PYTHONPATH has src?", any("src" in p for p in sys.path))

# Load .env from project root (works no matter CWD)
try:
    from dotenv import load_dotenv, find_dotenv
    env_path = find_dotenv(usecwd=True)
    load_dotenv(env_path, override=True)
    print(".env:", env_path or "NOT FOUND")
except Exception as e:
    print("dotenv err:", e)

# Show package versions (distribution names)
print("versions:",
      "langchain=", dist_ver("langchain"),
      "langchain-openai=", dist_ver("langchain-openai"),
      "openai=", dist_ver("openai"),
      "tiktoken=", dist_ver("tiktoken"))

from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
print("key_prefix:", repr(API_KEY[:6]), "len:", len(API_KEY))
assert API_KEY and len(API_KEY) > 20, "OPENAI_API_KEY not loaded!"

# 1) Direct LLM call
try:
    llm = ChatOpenAI(model=MODEL, api_key=API_KEY, temperature=0)
    print("Direct invoke:", llm.invoke("Say OK").content)
except Exception as e:
    print("Direct invoke FAILED:", type(e).__name__, e)
    traceback.print_exc()

# 2) Prompt → LLM → Parser chain
try:
    prompt = ChatPromptTemplate.from_template("Return just JSON: {{\"ok\": true}} for input: {x}")
    chain = prompt | llm | StrOutputParser()
    print("Chain invoke:", chain.invoke({"x": "test"}))
except Exception as e:
    print("Chain invoke FAILED:", type(e).__name__, e)
    traceback.print_exc()