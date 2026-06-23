# this file is to test the working of the llm model


from agent.llm_factory import get_llm

llm, info = get_llm()

print(info)

response = llm.invoke("What is NSS?")

print(response.content)



from agent.chatbot_langgraph import chat_with_ai

print(
    chat_with_ai(
        "Tell me about NSS"
    )
)

print(
    chat_with_ai(
        "Show upcoming activities"
    )
)