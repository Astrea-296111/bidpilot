from langgraph.graph import END, START, StateGraph

from bidpilot.agent.nodes import AgentNodes
from bidpilot.agent.state import BidState


def build_graph(settings, llm, rag, checkpointer):
    nodes = AgentNodes(settings, llm, rag)
    builder = StateGraph(BidState)
    builder.add_node("supervisor", nodes.supervisor)
    for name in ["parse", "analyst", "matcher", "reviewer", "score", "outline", "human_review", "save"]:
        builder.add_node(name, getattr(nodes, name))
        builder.add_edge(name, "supervisor")
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        lambda s: s.get("phase", "parse"),
        {
            **{
                n: n
                for n in [
                    "parse",
                    "analyst",
                    "matcher",
                    "reviewer",
                    "score",
                    "outline",
                    "human_review",
                    "save",
                ]
            },
            "stop": END,
        },
    )
    return builder.compile(checkpointer=checkpointer)
