"""Streamlit UI for the text-to-SQL agent.  Run: streamlit run app.py"""
import os

import pandas as pd
import streamlit as st

from agent import DB_PATH, build_graph, read_schema

st.set_page_config(page_title="Text-to-SQL Agent", page_icon="🗄️", layout="wide")
st.title("🗄️ Text-to-SQL Agent")
st.caption("Ask a question in plain English. A LangGraph agent writes, checks, runs and "
           "self-corrects the SQL, then explains the result.")

if not os.path.exists(DB_PATH):
    st.error(f"Database '{DB_PATH}' not found. Run `python setup_db.py` first.")
    st.stop()


@st.cache_resource
def get_graph():
    return build_graph()


with st.sidebar:
    st.subheader("Database schema")
    st.code(read_schema().split("-- sample")[0], language="sql")
    st.subheader("Try these")
    examples = [
        "How many customers are there in each city?",
        "Top 5 products by total revenue",
        "Which customer spent the most overall?",
        "Monthly number of orders in 2024",
        "Average order quantity per product category",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state["q"] = ex

question = st.text_input("Your question", key="q", placeholder="e.g. Top 5 products by revenue")

if st.button("Run", type="primary") and question.strip():
    graph = get_graph()
    final = {}
    with st.status("Agent working...", expanded=True) as status:
        for event in graph.stream({"question": question}, stream_mode="updates"):
            for node, update in event.items():
                final.update(update)
                msg = f"**{node}**"
                if update.get("error"):
                    msg += f" ⚠️ {update['error']}"
                st.write(msg)
        status.update(label="Done", state="complete")

    if final.get("status") == "ok":
        st.success(final["answer"])
        st.subheader("Generated SQL")
        st.code(final["sql"], language="sql")
        st.subheader("Result")
        st.dataframe(pd.DataFrame(final["rows"], columns=final["columns"]),
                     use_container_width=True)
        st.caption(f"Attempts used: {final.get('attempts')}")
    else:
        st.error(final.get("answer", "Something went wrong."))
