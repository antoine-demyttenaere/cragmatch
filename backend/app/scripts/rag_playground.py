"""Stage 6 learning playground: one function per step.

Run a single step:
    uv run python -m app.scripts.rag_playground 6.2
    uv run python -m app.scripts.rag_playground 6.4
    uv run python -m app.scripts.rag_playground 6.5
    uv run python -m app.scripts.rag_playground 6.8 [share_code]
    uv run python -m app.scripts.rag_playground 6.9a [share_code]   (also 6.9b, 6.9c)
    uv run python -m app.scripts.rag_playground 6.10 [share_code ...]
    uv run python -m app.scripts.rag_playground 6.11 [share_code] [answer ...]   (yes, or no:<reason>)

Steps from 6.8 on build the LangGraph trip planner and can take an argument.
Steps 6.3 and 6.6 compared Stage 3 with LangChain and were removed in ticket
014; the other numbers are kept so they match the plans in tickets/.

Steps that call Voyage say how many requests they make: the free tier
allows 3 per minute.
"""

import sys
from pprint import pprint
from typing import Callable
from uuid import uuid4

from langchain_core.output_parsers import StrOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.agent.graph import build_trip_planner
from app.agent.nodes import find_stays, merge_group_preferences, pick_sector, search_sectors
from app.agent.state import PlannerContext, TripState, initial_state
from app.core.database import SessionLocal
from app.rag.chain import RAG_PROMPT, build_rag_chain, format_docs
from app.rag.llm import get_chat_model
from app.rag.loader import SectorLoader
from app.rag.vectorstore import get_vector_store


def show(title, docs):
    print(f"\n=== {title}: {len(docs)} documents ===")
    for doc in docs:
        print(f"[{len(doc.page_content):>3} chars] {doc.metadata}")
        print(f"            {doc.page_content!r}")


def step_6_2():
    """Load sectors as Documents, then split them. No Voyage calls."""
    db = SessionLocal()
    try:
        docs = SectorLoader(db).load()
    finally:
        db.close()
    print(f"Loaded {len(docs)} sectors")
    show("First 3 loaded", docs[:3])

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = splitter.split_documents(docs)
    print(f"\nchunk_size=1000: {len(docs)} documents in -> {len(chunks)} chunks out")

    tiny = RecursiveCharacterTextSplitter(chunk_size=60, chunk_overlap=15, add_start_index=True)
    tiny_chunks = tiny.split_documents(docs)
    print(f"chunk_size=60:   {len(docs)} documents in -> {len(tiny_chunks)} chunks out")
    show("Sector 1 in tiny chunks", [c for c in tiny_chunks if c.metadata["sector_id"] == 1])


def step_6_4():
    """Three retriever modes. 3 Voyage calls (one per invoke)."""
    store = get_vector_store()

    retriever = store.as_retriever(search_kwargs={"k": 5})
    docs = retriever.invoke("somewhere good for kids and beginners")
    print("\n=== Step 6.4a: plain retriever ===")
    print("returns:", type(docs).__name__, "of", type(docs[0]).__name__)
    for doc in docs:
        print(f"  {doc.id:<10} {doc.metadata['name']:<12} ({doc.metadata['crag']})")

    siurana_only = store.as_retriever(search_kwargs={"k": 3, "filter": {"crag": {"$eq": "Siurana"}}})
    print("\n=== Step 6.4b: filtered to crag = Siurana ===")
    for doc in siurana_only.invoke("quiet crag, short approach"):
        print(f"  {doc.metadata['name']}")

    confident = store.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": 5, "score_threshold": 0.5},
    )
    print("\n=== Step 6.4c: only relevance >= 0.5 ===")
    for doc in confident.invoke("shady spot for a hot summer day"):
        print(f"  {doc.metadata['name']}")


def step_6_5(query: str = "quiet crag with a short approach, good for a beginner", k: int = 3):
    """The RAG chain piece by piece, then composed. 2 Voyage calls, 2 Claude calls."""
    retriever = get_vector_store().as_retriever(search_kwargs={"k": k})
    llm = get_chat_model()

    docs = retriever.invoke(query)   # Voyage call 1
    print(f"\n=== Step 6.5a: retriever returns {len(docs)} documents ===")
    for doc in docs:
        print(f"  {doc.metadata['name']} ({doc.metadata['crag']})")
        print(f"    {doc.page_content!r}")

    context = format_docs(docs)
    prompt_value = RAG_PROMPT.invoke({"context": context, "question": query})
    print("\n=== Step 6.5b: the filled prompt, as Claude receives it ===")
    for message in prompt_value.to_messages():
        print(f"[{message.type}]\n{message.content}\n")

    message = llm.invoke(prompt_value)   # Claude call 1
    print("=== Step 6.5c: the model's reply ===")
    print(type(message).__name__)
    print(message.content)
    print("usage_metadata:", message.usage_metadata)
    print("stop_reason:", message.response_metadata.get("stop_reason"))

    answer = StrOutputParser().invoke(message)
    print("\n=== Step 6.5d: after StrOutputParser ===")
    print(answer)

    chain_answer = build_rag_chain(retriever, llm).invoke(query)   # Voyage call 2, Claude call 2
    print("\n=== Step 6.5e: the composed chain, same query ===")
    print(chain_answer)


def step_6_8(share_code: str = "9JS3VA3C"):
    """A graph with no nodes (START -> END): the state comes out as it went in. No network."""
    builder = StateGraph(TripState, context_schema=PlannerContext)
    builder.add_edge(START, END)
    graph = builder.compile()

    state = initial_state(share_code)
    with SessionLocal() as db:
        result = graph.invoke(state, context=PlannerContext(db=db))

    print("\n=== Step 6.8: initial state ===")
    pprint(state)
    print("\n=== Step 6.8: state after the graph ===")
    pprint(result)
    print("\nSame dict: no node ran, so nothing changed.")


def _run_line(share_code: str, *nodes: tuple[str, Callable]) -> dict:
    """Run the given nodes one after the other (START -> n1 -> n2 -> ... -> END)."""
    builder = StateGraph(TripState, context_schema=PlannerContext)
    previous = START
    for name, node in nodes:
        builder.add_node(name, node)
        builder.add_edge(previous, name)
        previous = name
    builder.add_edge(previous, END)
    graph = builder.compile()

    with SessionLocal() as db:
        return graph.invoke(initial_state(share_code), context=PlannerContext(db=db))


MERGE = ("merge_preferences", merge_group_preferences)
SEARCH = ("search_sectors", search_sectors)
PICK = ("pick_sector", pick_sector)
STAYS = ("find_stays", find_stays)


def _candidate_line(c: dict) -> str:
    return f"{c['sector_name']} ({c['crag_name']}, {c['distance_km']} km)"


def _stay_line(s: dict) -> str:
    return f"{s['stay']['name']} ({s['stay']['type']}, {s['distance_km']} km)"


def _print_state(title: str, state: dict) -> None:
    """Pprint the state with candidates and stays shortened to one line each."""
    shown = dict(state)
    if "candidates" in shown:
        shown["candidates"] = [_candidate_line(c) for c in shown["candidates"]]
    if shown.get("chosen_sector"):
        shown["chosen_sector"] = _candidate_line(shown["chosen_sector"])
    if "stays" in shown:
        shown["stays"] = [_stay_line(s) for s in shown["stays"]]
    print(f"\n=== {title} ===")
    pprint(shown)


def step_6_9a(share_code: str = "9JS3VA3C"):
    """One node: merge_preferences. No network."""
    _print_state("Step 6.9a: after merge_preferences", _run_line(share_code, MERGE))


def step_6_9b(share_code: str = "9JS3VA3C"):
    """Two nodes: merge, then search. Nothing from step 6.9a is lost. No network."""
    _print_state("Step 6.9b: after search_sectors", _run_line(share_code, MERGE, SEARCH))


def step_6_9c(share_code: str = "9JS3VA3C"):
    """Four nodes: merge, search, pick_sector, then find_stays. No network."""
    print("Note: since 6.11 picking the sector is its own node (pick_sector), not part of search.")
    _print_state(
        "Step 6.9c: after find_stays", _run_line(share_code, MERGE, SEARCH, PICK, STAYS)
    )


def step_6_10(*share_codes: str):
    """The routed graph: print its diagram, then run one group per code. No network."""
    # A checkpointer, because a group with common ground now pauses at approve_sector.
    graph = build_trip_planner(InMemorySaver())
    print("\n=== Step 6.10: diagram (paste into a mermaid block) ===")
    print(graph.get_graph().draw_mermaid())

    for code in share_codes or ("9JS3VA3C",):
        path = []
        config = {"configurable": {"thread_id": str(uuid4())}}
        with SessionLocal() as db:
            updates = graph.stream(
                initial_state(code),
                config,
                context=PlannerContext(db=db),
                stream_mode="updates",
            )
            state: dict = {}
            for update in updates:
                for node, changes in update.items():
                    if node == "__interrupt__":
                        path.append("paused at approve_sector (step 6.11 answers it)")
                        continue
                    path.append(node)
                    state.update(changes)
        print(f"\n=== Step 6.10: group {code} ===")
        print(" -> ".join(path))
        if state.get("message"):
            print(state["message"])
        else:
            print("Stays:", [_stay_line(s) for s in state.get("stays", [])])


def _parse_answer(answer: str) -> dict:
    """'yes' -> approved; 'no' or 'no:<reason>' -> rejected."""
    if answer.lower() == "yes":
        return {"approved": True}
    _, _, reason = answer.partition(":")
    return {"approved": False, "reason": reason}


def step_6_11(share_code: str = "9JS3VA3C", *answers: str):
    """Pause at approve_sector, then answer: yes, or no:<reason>. No network.

    Example: 6.11 <code> "no:too far" yes
    """
    graph = build_trip_planner(InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid4())}}

    with SessionLocal() as db:
        # context= is passed again on every call: it isn't saved in the checkpoint.
        context = PlannerContext(db=db)
        output = graph.invoke(initial_state(share_code), config, context=context)
        print("\n=== Step 6.11: first run ===")

        for answer in answers:
            if "__interrupt__" not in output:
                break
            question = output["__interrupt__"][0].value
            print("Paused. Question:", question["question"])
            print("Proposed:", _candidate_line(question["sector"]))
            snapshot = graph.get_state(config)
            print("next =", snapshot.next)
            print("chosen_sector =", _candidate_line(snapshot.values["chosen_sector"]))
            print("There is no 'stays' key yet:", "stays" not in snapshot.values)

            print(f"\n--- answer: {answer} ---")
            output = graph.invoke(Command(resume=_parse_answer(answer)), config, context=context)

        if "__interrupt__" in output:
            question = output["__interrupt__"][0].value
            print("Still paused on:", _candidate_line(question["sector"]))
        elif output.get("plan"):
            plan = output["plan"]
            print("\nPlan:", _candidate_line(plan["sector"]))
            print("Dates:", plan["checkin"], "to", plan["checkout"], "for", plan["guests"])
            print("Stays:", [_stay_line(s) for s in plan["stays"]])
            print("Links:", plan["links"])
        else:
            print("\nNo plan:", output.get("message"))
        print("Rejections:", output.get("rejections"))


STEPS = {
    "6.2": step_6_2,
    "6.4": step_6_4,
    "6.5": step_6_5,
    "6.8": step_6_8,
    "6.9a": step_6_9a,
    "6.9b": step_6_9b,
    "6.9c": step_6_9c,
    "6.10": step_6_10,
    "6.11": step_6_11,
}


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else None
    if step not in STEPS:
        print(f"Usage: python -m app.scripts.rag_playground <step> [args]   (steps: {', '.join(STEPS)})")
        sys.exit(1)
    STEPS[step](*sys.argv[2:])
