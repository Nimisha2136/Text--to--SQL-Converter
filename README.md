# Text-to-SQL Agent (Minor Project)

Ask questions in plain English → an **agentic AI workflow** writes the SQL, checks it,
runs it, fixes its own mistakes, and explains the result.

## Agentic AI framework used
**LangGraph** (built on LangChain) models the agent as a graph of nodes with
conditional routing, and **langchain-anthropic** connects the Claude LLM.

```
get_schema → generate_sql → validate_sql → execute_sql → summarize → END
                  ↑               │              │
                  └───── retry ───┴──────────────┘   (max 3 attempts, else give_up)
```

| Node | Role |
|------|------|
| `get_schema` | Reads tables, columns and sample rows from the DB |
| `generate_sql` | LLM writes SQL; on retry it also sees the previous SQL + error |
| `validate_sql` | Guardrail: only a single SELECT, blocks DROP/DELETE/UPDATE etc. |
| `execute_sql` | Tool call on a **read-only** SQLite connection |
| `summarize` | LLM explains the rows in plain English |

Agentic features: **tool use, state, conditional routing, self-correction loop, guardrails.**

## Project structure
```
text2sql-agent/
├── agent.py          # LangGraph agent (core logic)
├── app.py            # Streamlit web UI
├── setup_db.py       # Creates sample.db (customers, products, orders)
├── requirements.txt
└── .env.example
```

## Setup
```bash
python -m venv venv
venv\Scripts\activate            # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt

cp .env.example .env             # then put your ANTHROPIC_API_KEY inside
python setup_db.py               # creates sample.db
streamlit run app.py             # opens the web app
```
CLI alternative: `python agent.py`

## Example questions
- How many customers are there in each city?
- Top 5 products by total revenue
- Which customer spent the most overall?
- Monthly number of orders in 2024

## Use your own database
Set `DB_PATH` in `.env` to any SQLite file. The agent reads its schema automatically.

## Ideas to extend (for viva / next version)
- Add MySQL/PostgreSQL support with SQLAlchemy
- Chart generation node (matplotlib/plotly) for numeric results
- Conversation memory for follow-up questions ("now only for Delhi")
- Schema-linking node for large databases
- Evaluate accuracy on the Spider benchmark
