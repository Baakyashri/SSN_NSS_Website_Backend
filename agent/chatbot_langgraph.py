from langchain_core.messages import HumanMessage

from agent.graph import graph


def chat_with_ai(message):

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(content=message)
            ]
        }
    )

    final_message = result["messages"][-1]

    return final_message.content