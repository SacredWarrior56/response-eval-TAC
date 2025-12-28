"""
LangGraph + Tavily Research Agent
NO silent failures
NO hanging
NO mystery behavior
"""

from dotenv import load_dotenv
load_dotenv()

from typing import TypedDict, List, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langchain_core.messages import HumanMessage
import sys

# -----------------------------
# Agent State
# -----------------------------
class AgentState(TypedDict):
    query: str
    plan: List[str]
    search_results: List[Any]
    answer: str

# -----------------------------
# Models & Tools
# -----------------------------
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

tavily = TavilySearch(
    max_results=5,
    search_depth="advanced"
)

# -----------------------------
# Nodes
# -----------------------------
def planner(state: AgentState):
    print("\n[PLANNER] Creating research plan...", flush=True)

    prompt = f"""
Break the query into 3–5 focused web search tasks.
Return ONLY a numbered list.

Query:
{state['query']}
"""
    resp = llm.invoke([HumanMessage(content=prompt)])

    plan = [
        line.split(".", 1)[1].strip() if "." in line else line.strip()
        for line in resp.content.splitlines()
        if line.strip()
    ]

    print(f"[PLANNER] Tasks: {plan}", flush=True)
    return {"plan": plan}


def search(state: AgentState):
    print("\n[SEARCH] Running Tavily searches...", flush=True)

    results = []
    for task in state["plan"]:
        print(f"  → Searching: {task}", flush=True)
        try:
            res = tavily.run(task)   # ✅ CORRECT CALL
            results.append(res)
        except Exception as e:
            print(f"  ✖ Tavily error: {e}", file=sys.stderr, flush=True)

    if not results:
        raise RuntimeError("Tavily returned no results")

    return {"search_results": results}


def synthesize(state: AgentState):
    print("\n[SYNTHESIS] Generating final answer...", flush=True)

    prompt = f"""
Answer the query using the search results.
Be analytical.
Cite sources inline (URLs).

Query:
{state['query']}

Search results:
{state['search_results']}
"""
    resp = llm.invoke([HumanMessage(content=prompt)])
    return {"answer": resp.content}

# -----------------------------
# Graph
# -----------------------------
graph = StateGraph(AgentState)

graph.add_node("planner", planner)
graph.add_node("search", search)
graph.add_node("synthesize", synthesize)

graph.set_entry_point("planner")
graph.add_edge("planner", "search")
graph.add_edge("search", "synthesize")
graph.add_edge("synthesize", END)

app = graph.compile()

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    query = """
whats the current temperature in udupi. what was the lowest temperature and the highest temperature ever witnessed and what was the latest news from this place?
"""

    print("\n[START] Agent running...\n", flush=True)

    result = app.invoke({"query": query})

    print("\n================ FINAL ANSWER ================\n")
    print(result["answer"])
