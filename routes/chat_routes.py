from flask import Blueprint, request, jsonify

from agents.chatbot import chat_with_ai

chat_bp = Blueprint(
    "chat",
    __name__
)


@chat_bp.route("/chat", methods=["POST"])
def chat():

    try:

        data = request.get_json()

        messages = data.get(
            "messages",
            []
        )

        response = chat_with_ai(
            messages
        )

        return jsonify({
            "response": response
        })

    except Exception as e:

        print("CHAT ERROR:")
        print(e)

        return jsonify({
            "error": str(e)
        }), 500