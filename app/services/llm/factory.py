from app.services.llm.provider import GenericLLMProvider


def get_llm_provider():
    return GenericLLMProvider()