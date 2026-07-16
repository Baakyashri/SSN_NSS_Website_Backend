"""
agent/graph.py
--------------
Updated graph flow:

    START → agent → tools → verify → agent → ... → END

The verify node sits between tools and agent. After any mutate_record
insert, it re-queries the database to confirm the write actually
happened, before looping back to the agent. This makes the agent's
"success" claims grounded in verified reality instead of trusted
LLM output.

MemorySaver checkpointer still provides in-session conversation
memory, scoped per user via thread_id. Memory lives in RAM — cleared
on server restart, never persisted to disk or database.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import tools_condition
from langgraph.checkpoint.memory import MemorySaver

from agent.state import AgentState
from agent.nodes.agent_node import agent_node
from agent.nodes.tool_node import tool_node
from agent.nodes.verify_node import verify_node


graph_builder = StateGraph(AgentState)

graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", tool_node)
graph_builder.add_node("verify", verify_node)

graph_builder.add_edge(START, "agent")

graph_builder.add_conditional_edges(
    "agent",
    tools_condition,
    {
        "tools": "tools",
        END    : END,
    }
)

# ── Tools always route through verify before returning to agent ──
# verify_node checks: was this a mutate_record insert? if so, confirm
# the document actually exists in the database before the agent
# speaks to the user about it.
graph_builder.add_edge("tools", "verify")
graph_builder.add_edge("verify", "agent")

# ── MemorySaver keeps conversation history in RAM per thread_id ──
memory = MemorySaver()

graph = graph_builder.compile(checkpointer=memory)