"""A deterministic LangGraph tool boundary over real loopback HTTP. No LLM required."""

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, TypedDict

from langgraph.graph import END, START, StateGraph

from commitlatch import CommitLatch, SQLiteLedger, UnknownOutcome
from commitlatch.http_demo import DemoHTTPAdapter, HTTPFixture


class State(TypedDict, total=False):
    business_key: str
    arguments: Dict[str, Any]
    outcome: str
    result: Any


def build_graph(engine, adapter):
    def dispatch(state):
        try:
            receipt = engine.run("langgraph-demo", state["business_key"], adapter, state["arguments"])
            return {"outcome": "SUCCEEDED", "result": receipt}
        except UnknownOutcome:
            return {"outcome": "UNKNOWN", "result": None}

    def reconcile(state):
        action = engine.reconcile("langgraph-demo", state["business_key"], adapter)
        return {"outcome": action["state"], "result": action["result"]}

    builder = StateGraph(State)
    builder.add_node("dispatch", dispatch)
    builder.add_node("reconcile", reconcile)
    builder.add_edge(START, "dispatch")
    builder.add_conditional_edges("dispatch", lambda state: state["outcome"],
                                  {"UNKNOWN": "reconcile", "SUCCEEDED": END})
    builder.add_edge("reconcile", END)
    # Graph checkpoints are deliberately not part of this example. The action
    # ledger survives reconstruction of the graph and its CommitLatch instance.
    return builder.compile()


def run(opaque=False):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with HTTPFixture(root / "provider.db", observable=not opaque) as provider:
            adapter = DemoHTTPAdapter(provider)
            ledger_path = str(root / "ledger.db")
            request = {"business_key": "order-42/refund-request-1",
                       "arguments": {"operation": "refund", "amount_minor": 1200}}
            first = build_graph(CommitLatch(SQLiteLedger(ledger_path)), adapter).invoke(request)
            second = build_graph(CommitLatch(SQLiteLedger(ledger_path)), adapter).invoke(request)
            stats = provider.snapshot()
            expected = "UNKNOWN" if opaque else "SUCCEEDED"
            if first["outcome"] != expected or second["outcome"] != expected:
                raise RuntimeError("Unexpected graph outcome")
            if stats["effects"] != 1 or stats["post_requests"] != 1:
                raise RuntimeError("Graph redispatched the same business operation")
            if not opaque and first["result"] != second["result"]:
                raise RuntimeError("Repeated invocation did not return the same receipt")
            result = dict(first=first["outcome"], repeated=second["outcome"], **stats)
            print(json.dumps(result, indent=2))
            return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opaque", action="store_true", help="Make receipt lookup unavailable")
    run(parser.parse_args().opaque)
