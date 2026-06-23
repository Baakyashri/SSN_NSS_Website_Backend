from langgraph.prebuilt import ToolNode

from agent.tools.activity_tools import get_upcoming_events


TOOLS = [
    get_upcoming_events
]

tool_node = ToolNode(TOOLS)