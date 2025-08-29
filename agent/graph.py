"""LangGraph single-node graph template.

Returns a predefined response. Replace logic and configuration as needed.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END
from langgraph.graph import StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from nodes.node import retrieve, generate, analyze_and_classify, ContextSchema

graph_builder = StateGraph(MessagesState, context_schema=ContextSchema)
tools = ToolNode([retrieve])
graph_builder.add_node("tools", tools)
graph_builder.add_node("generate", generate)
graph_builder.add_node("analyze_and_classify", analyze_and_classify)

graph_builder.add_conditional_edges(
    "analyze_and_classify",
    tools_condition,
    {END: END, "tools": "tools"},
)
graph_builder.add_edge("tools", "generate")
graph_builder.add_edge("generate", END)

graph_builder.set_entry_point("analyze_and_classify")

# graph_builder.add_conditional_edges(
#     "spacer_node",
#     stop_condition,
#     {True: END, False: "analyze_and_classify"}
# )

memory = MemorySaver()
graph = graph_builder.compile()
