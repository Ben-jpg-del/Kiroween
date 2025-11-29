"""LLM provider configuration."""

from langchain_openai import ChatOpenAI

from kiroween.config import get_settings
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


def get_llm() -> ChatOpenAI:
    """Get configured LLM instance.

    Returns:
        ChatOpenAI instance configured with settings.
    """
    settings = get_settings()

    logger.debug("initializing_llm", model=settings.llm_model)

    return ChatOpenAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=settings.openai_api_key,
    )


def get_llm_with_tools(tools: list) -> ChatOpenAI:
    """Get LLM instance with tools bound.

    Args:
        tools: List of tools to bind to the LLM.

    Returns:
        ChatOpenAI instance with tools bound.
    """
    llm = get_llm()
    return llm.bind_tools(tools)
