import os

from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


# ==========================================================
# MODEL PRIORITY LIST
# ==========================================================

MODEL_PRIORITY = [

    # =========================
    # GROQ MODELS
    # =========================

    {
        "provider": "groq",
        "model": "meta-llama/llama-4-scout-17b-16e-instruct"
    },

    {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile"
    },

    {
        "provider": "groq",
        "model": "qwen/qwen3-32b"
    },

    {
        "provider": "groq",
        "model": "openai/gpt-oss-120b"
    },

    {
        "provider": "groq",
        "model": "openai/gpt-oss-20b"
    },

    # =========================
    # GEMINI MODELS
    # Replace names if your
    # actual API model ids differ
    # =========================

    {
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite"
    },

    {
        "provider": "gemini",
        "model": "gemini-2.5-flash-lite"
    },

    {
        "provider": "gemini",
        "model": "gemini-3.5-flash"
    },

    {
        "provider": "gemini",
        "model": "gemini-3-flash"
    },

    {
        "provider": "gemini",
        "model": "gemini-2.5-flash"
    }
]


# ==========================================================
# CACHE ACTIVE MODEL
# ==========================================================

_active_llm = None
_active_provider = None
_active_model = None


# ==========================================================
# CREATE LLM
# ==========================================================

def _create_llm(provider, model):

    if provider == "groq":

        return ChatGroq(
            model=model,
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0
        )

    elif provider == "gemini":

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0
        )

    else:
        raise ValueError(f"Unsupported provider: {provider}")


# ==========================================================
# FIND FIRST WORKING MODEL
# ==========================================================

def get_llm():

    global _active_llm
    global _active_provider
    global _active_model

    # Reuse already selected model
    if _active_llm is not None:

        return (
            _active_llm,
            {
                "provider": _active_provider,
                "model": _active_model
            }
        )

    print("\n")
    print("=" * 60)
    print("NSS AI AGENT - LLM FACTORY")
    print("=" * 60)

    for config in MODEL_PRIORITY:

        provider = config["provider"]
        model = config["model"]

        try:

            print(f"\nTrying -> {provider.upper()} | {model}")

            llm = _create_llm(provider, model)

            # Small test call
            llm.invoke("hello")

            _active_llm = llm
            _active_provider = provider
            _active_model = model

            print("\nSUCCESS")
            print("-" * 60)
            print(f"Provider : {provider}")
            print(f"Model    : {model}")
            print("-" * 60)

            return (
                _active_llm,
                {
                    "provider": _active_provider,
                    "model": _active_model
                }
            )

        except Exception as e:

            print(f"FAILED -> {model}")
            print(str(e))
            continue

    raise Exception(
        "No available LLM models found. "
        "All configured providers failed."
    )


# ==========================================================
# FORCE SWITCH TO NEXT MODEL
# ==========================================================

def switch_model():

    global _active_llm
    global _active_provider
    global _active_model

    current_model = _active_model

    _active_llm = None
    _active_provider = None
    _active_model = None

    found_current = False

    for config in MODEL_PRIORITY:

        if found_current:

            try:

                provider = config["provider"]
                model = config["model"]

                llm = _create_llm(provider, model)

                llm.invoke("hello")

                _active_llm = llm
                _active_provider = provider
                _active_model = model

                print("\nMODEL SWITCHED")
                print("-" * 60)
                print(f"Provider : {provider}")
                print(f"Model    : {model}")
                print("-" * 60)

                return _active_llm

            except Exception:
                continue

        if config["model"] == current_model:
            found_current = True

    raise Exception("No fallback model available.")