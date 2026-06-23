from langchain_core.messages import SystemMessage

from agent.llm_factory import get_llm
from agent.prompts.system_prompt import SYSTEM_PROMPT

from agent.tools.activity_tools import get_upcoming_events


TOOLS = [
    get_upcoming_events
]

llm, llm_info = get_llm()

llm_with_tools = llm.bind_tools(TOOLS)


def agent_node(state):

    messages = state["messages"]

    response = llm_with_tools.invoke(
        [SystemMessage(content=SYSTEM_PROMPT)] +
        messages
    )

    return {
        "messages": [response]
    }