from langgraph.graph import StateGraph
from langgraph.graph import START, END
from langgraph.prebuilt import tools_condition

from agent.state import AgentState
from agent.nodes.agent_node import agent_node
from agent.nodes.tool_node import tool_node


graph_builder = StateGraph(AgentState)

graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", tool_node)


graph_builder.add_edge(START, "agent")

graph_builder.add_conditional_edges(
    "agent",
    tools_condition,
    {
        "tools": "tools",
        END: END
    }
)

graph_builder.add_edge("tools", "agent")


graph = graph_builder.compile()