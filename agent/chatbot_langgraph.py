"""
agent/chatbot_langraph.py
--------------------------
Each user gets a unique thread_id so MemorySaver tracks their
conversation separately in RAM.

thread_id = user_id  — simple, unique per user, no extra setup needed.

The chat route passes user_id decoded from JWT, so every message
from the same logged-in user continues the same conversation thread.
"""

from langchain_core.messages import HumanMessage

from agent.graph import graph


def chat_with_ai(
    message   : str,
    user_id   : str,
    user_email: str,
    role      : str = "volunteer",
    session_id:str="",
) -> str:
    """
    Invoke the LangGraph agent with in-session memory.

    Each user_id gets its own conversation thread via MemorySaver.
    Memory is RAM-only — no DB writes, cleared on server restart or logout.

    Args:
        message    : Latest message the user typed.
        user_id    : From JWT — used as thread_id so memory is per-user.
        user_email : From JWT — passed to tools for notifications.
        role       : "volunteer" or "admin".

    Returns:
        Agent's final response as a plain string.
    """
    # Use session_id if provided, else fall back to user_id
    thread_id = f"{user_id}_{session_id}" if session_id else user_id

    result = graph.invoke(
        {
            "messages": [HumanMessage(content=message)],
        },
        config={
            "configurable": {
                # ── thread_id scopes memory to this user ──────
                # MemorySaver uses this to store and retrieve
                # the conversation history for each user separately.
                "thread_id": user_id,

                # ── user context for tools ────────────────────
                "user_id"   : user_id,
                "user_email": user_email,
                "role"      : role,
            }
        },
    )

    final_message = result["messages"][-1]
    return final_message.content