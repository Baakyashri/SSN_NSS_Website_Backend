import os
from dotenv import load_dotenv
from agent.prompts.system_prompt import SYSTEM_PROMPT
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage,AIMessage,SystemMessage,ToolMessage

from agent.tools.activity_tools import get_upcoming_events

load_dotenv()



llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY")
)

tools = [get_upcoming_events]

tool_map = {
    tool.name: tool
    for tool in tools
}

llm_with_tools = llm.bind_tools(tools)


def build_langchain_messages(frontend_messages):

    messages = [
        SystemMessage(content=SYSTEM_PROMPT)
    ]

    for msg in frontend_messages:

        role = msg.get("role")
        content = msg.get("content", "")

        if role == "user":
            messages.append(
                HumanMessage(content=content)
            )

        elif role == "assistant":
            messages.append(
                AIMessage(content=content)
            )
        
        messages = messages[-10:]

    return messages


def normalize_content(content):

    if isinstance(content, str):
        return content

    if isinstance(content, list):

        texts = []

        for item in content:

            if isinstance(item, dict):
                texts.append(
                    item.get("text", "")
                )

        return "\n".join(texts)

    return str(content)


def chat_with_ai(frontend_messages):

    messages = build_langchain_messages(
        frontend_messages
    )

    response = llm_with_tools.invoke(messages)

    print("\n===== INITIAL RESPONSE =====")
    print(response)

    if not response.tool_calls:

        return normalize_content(
            response.content
        )

    tool_messages = []

    for tool_call in response.tool_calls:

        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        print(f"\nExecuting Tool: {tool_name}")
        print(f"Arguments: {tool_args}")

        result = tool_map[tool_name].invoke(
            tool_args
        )

        print("Tool Result:")
        print(result)

        tool_messages.append(
            ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"]
            )
        )

    final_response = llm_with_tools.invoke(
        [
            *messages,
            response,
            *tool_messages
        ]
    )

    print("\n===== FINAL RESPONSE =====")
    print(final_response)

    return normalize_content(
        final_response.content
    )