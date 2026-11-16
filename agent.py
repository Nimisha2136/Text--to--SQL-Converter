"""
Text-to-SQL agent built with LangGraph.

Workflow (each box is a graph node):

  get_schema -> generate_sql -> validate_sql -> execute_sql -> summarize
                     ^               |               |
                     +---- retry ----+---------------+   (self-correction loop)
"""
import os
import re
import sqlite3
from typing import Any, Optional, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "sample.db")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-5-5")
MAX_ATTEMPTS = 3
ROW_LIMIT = 200

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|pragma|vacuum)\b",
    re.IGNORECASE,
)


class AgentState(TypedDict, total=False):
    question: str
    schema: str
    sql: str
    error: Optional[str]
    columns: list
    rows: list
    attempts: int
    answer: str
    status: str  # "ok" | "failed"


# ----------------------------------------------------------------- helpers
def get_llm():
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=os.getenv("MODEL_NAME", "qwen2.5-coder:7b"), temperature=0)

    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=os.getenv("MODEL_NAME", "llama-3.3-70b-versatile"), temperature=0)

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=os.getenv("MODEL_NAME", "gemini-2.0-flash"), temperature=0)

    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model=MODEL_NAME, temperature=0, max_tokens=1000)


def _text(response) -> str:
    """Normalise an LLM response to plain text."""
    content = response.content
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content)


def clean_sql(text: str) -> str:
    text = re.sub(r"```(?:sql)?", "", text, flags=re.IGNORECASE).replace("```", "")
    return text.strip().rstrip(";").strip()


def read_schema(db_path: str = DB_PATH) -> str:
    con = sqlite3.connect(db_path)
    parts = []
    for (name, ddl) in con.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        sample = con.execute(f"SELECT * FROM {name} LIMIT 2").fetchall()
        parts.append(f"{ddl}\n-- sample rows: {sample}")
    con.close()
    return "\n\n".join(parts)


# ------------------------------------------------------------------ graph
def build_graph(llm: Any = None, db_path: str = DB_PATH):
    llm = llm or get_llm()

    # Node 1: look at the database
    def get_schema(state: AgentState):
        return {"schema": read_schema(db_path), "attempts": 0, "error": None}

    # Node 2: LLM writes (or repairs) the SQL
    def generate_sql(state: AgentState):
        system = (
            "You are an expert SQLite analyst. Write ONE read-only SQLite SELECT query "
            "that answers the user's question using only the schema provided. "
            "Return ONLY the SQL, no explanation, no markdown."
        )
        user = f"Schema:\n{state['schema']}\n\nQuestion: {state['question']}"
        if state.get("error"):
            user += (
                f"\n\nYour previous query was:\n{state['sql']}\n"
                f"It failed with: {state['error']}\nFix it and return the corrected SQL only."
            )
        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return {"sql": clean_sql(_text(resp)), "attempts": state.get("attempts", 0) + 1,
                "error": None}

    # Node 3: safety guardrail (tool-use policy)
    def validate_sql(state: AgentState):
        sql = state["sql"]
        if not re.match(r"^\s*(select|with)\b", sql, re.IGNORECASE):
            return {"error": "Only SELECT queries are allowed."}
        if ";" in sql:
            return {"error": "Multiple statements are not allowed."}
        if FORBIDDEN.search(sql):
            return {"error": "Query contains a forbidden keyword (read-only mode)."}
        return {"error": None}

    # Node 4: tool call – run SQL on a READ-ONLY connection
    def execute_sql(state: AgentState):
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = con.execute(state["sql"])
            rows = cur.fetchmany(ROW_LIMIT)
            cols = [d[0] for d in cur.description]
            con.close()
            return {"columns": cols, "rows": rows, "error": None}
        except Exception as e:  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}"}

    # Node 5: explain results in plain English
    def summarize(state: AgentState):
        preview = state["rows"][:20]
        prompt = (
            f"Question: {state['question']}\nSQL: {state['sql']}\n"
            f"Columns: {state['columns']}\nRows (up to 20): {preview}\n\n"
            "Answer the question in 1-3 clear sentences based only on these rows."
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        return {"answer": _text(resp).strip(), "status": "ok"}

    def give_up(state: AgentState):
        return {"status": "failed",
                "answer": f"Could not produce a working query after {MAX_ATTEMPTS} attempts. "
                          f"Last error: {state.get('error')}"}

    # Routing: the 'agentic' decision points
    def after_validate(state: AgentState):
        if not state.get("error"):
            return "execute_sql"
        return "generate_sql" if state["attempts"] < MAX_ATTEMPTS else "give_up"

    def after_execute(state: AgentState):
        if not state.get("error"):
            return "summarize"
        return "generate_sql" if state["attempts"] < MAX_ATTEMPTS else "give_up"

    g = StateGraph(AgentState)
    for name, fn in [("get_schema", get_schema), ("generate_sql", generate_sql),
                     ("validate_sql", validate_sql), ("execute_sql", execute_sql),
                     ("summarize", summarize), ("give_up", give_up)]:
        g.add_node(name, fn)

    g.set_entry_point("get_schema")
    g.add_edge("get_schema", "generate_sql")
    g.add_edge("generate_sql", "validate_sql")
    g.add_conditional_edges("validate_sql", after_validate,
                            ["execute_sql", "generate_sql", "give_up"])
    g.add_conditional_edges("execute_sql", after_execute,
                            ["summarize", "generate_sql", "give_up"])
    g.add_edge("summarize", END)
    g.add_edge("give_up", END)
    return g.compile()


def ask(question: str, graph=None) -> dict:
    graph = graph or build_graph()
    return graph.invoke({"question": question})


if __name__ == "__main__":  # quick CLI: python agent.py
    q = input("Ask a question about the database: ")
    out = ask(q)
    print("\nSQL   :", out.get("sql"))
    print("Rows  :", out.get("rows", [])[:10])
    print("Answer:", out["answer"])
