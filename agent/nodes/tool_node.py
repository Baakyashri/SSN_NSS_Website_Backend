"""
agent/nodes/tool_node.py
-------------------------
ToolNode must have the same tools list as agent_node.
If a tool is in agent_node but not here, the agent calls it
but ToolNode has no handler for it — silent failure.
"""
from langgraph.prebuilt import ToolNode
from langchain_core.messages import ToolMessage

from agent.tools.activity_tools import get_upcoming_events
from agent.tools.generic_tools import (
    query_records,
    aggregate_records,
    get_volunteer_hours_summary,
    mutate_record,
    schedule_job,
    send_notification,
)
from agent.tools.report_tools import (
    semantic_search_reports,
    request_report,
)

TOOLS = [
    get_upcoming_events,
    query_records,
    aggregate_records,
    get_volunteer_hours_summary,
    mutate_record,
    schedule_job,
    send_notification,
    semantic_search_reports,
    request_report,
]

# Groq rejects empty tool message content — this handler ensures
# tool results always have non-empty string content
def safe_tool_node(state):
    tool_node_instance = ToolNode(TOOLS)
    result = tool_node_instance.invoke(state)

    # sanitise all tool messages — replace empty content with placeholder
    safe_messages = []
    for msg in result.get("messages", []):
        if hasattr(msg, "content"):
            if not msg.content or msg.content == [] or msg.content == "":
                msg.content = "Tool returned no results."
        safe_messages.append(msg)

    return {"messages": safe_messages}

tool_node = safe_tool_node