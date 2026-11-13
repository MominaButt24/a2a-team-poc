# import os
# from dataclasses import dataclass

# from dotenv import load_dotenv

# # Load environment variables
# load_dotenv()


# @dataclass
# class Settings:
#     llm_provider: str
#     anthropic_api_key: str
#     anthropic_model: str
#     anthropic_max_tokens: int
#     anthropic_temperature: float

#     max_child_agents: int

#     a2a_host: str
#     a2a_port_start: int


# def get_settings() -> Settings:

#     provider = os.getenv("LLM_PROVIDER", "anthropic")

#     if provider != "anthropic":
#         raise ValueError(f"Unsupported LLM provider: {provider}")

#     api_key = os.getenv("ANTHROPIC_API_KEY")

#     if not api_key or api_key == "your_company_api_key_here":
#         raise ValueError("ANTHROPIC_API_KEY is missing in .env")

#     return Settings(
#         llm_provider=provider,
#         anthropic_api_key=api_key,
#         anthropic_model=os.getenv(
#             "ANTHROPIC_MODEL", "claude-sonnet-4-5"
#         ),
#         anthropic_max_tokens=int(
#             os.getenv("ANTHROPIC_MAX_TOKENS", "2048")
#         ),
#         anthropic_temperature=float(
#             os.getenv("ANTHROPIC_TEMPERATURE", "0.2")
#         ),
#         max_child_agents=int(
#             os.getenv("MAX_CHILD_AGENTS", "4")
#         ),
#         a2a_host=os.getenv("A2A_HOST", "127.0.0.1"),
#         a2a_port_start=int(
#             os.getenv("A2A_PORT_START", "9001")
#         ),
#     )


# settings = get_settings()

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    llm_provider: str

    # Groq configuration
    groq_api_key: str
    groq_model: str
    groq_max_tokens: int

    # Anthropic configuration (kept as fallback)
    anthropic_api_key: str
    anthropic_model: str
    anthropic_max_tokens: int

    max_child_agents: int

    a2a_host: str
    a2a_port_start: int


def get_settings() -> Settings:

    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if provider not in ("groq", "anthropic"):
        raise ValueError(f"Unsupported LLM provider: {provider}")

    groq_api_key = os.getenv("GROQ_API_KEY", "")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if provider == "groq":
        if not groq_api_key or groq_api_key == "your_groq_api_key":
            raise ValueError("GROQ_API_KEY is missing in .env")

    if provider == "anthropic":
        if not anthropic_api_key or anthropic_api_key == "your_company_api_key_here":
            raise ValueError("ANTHROPIC_API_KEY is missing in .env")

    return Settings(
        llm_provider=provider,

        # Groq
        groq_api_key=groq_api_key,
        groq_model=os.getenv(
            "GROQ_MODEL", "openai/gpt-oss-20b"
        ),
        groq_max_tokens=int(
            os.getenv("GROQ_MAX_TOKENS", "2048")
        ),

        # Anthropic
        anthropic_api_key=anthropic_api_key,
        anthropic_model=os.getenv(
            "ANTHROPIC_MODEL", "claude-sonnet-4-5"
        ),
        anthropic_max_tokens=int(
            os.getenv("ANTHROPIC_MAX_TOKENS", "2048")
        ),

        max_child_agents=int(
            os.getenv("MAX_CHILD_AGENTS", "4")
        ),

        a2a_host=os.getenv("A2A_HOST", "127.0.0.1"),
        a2a_port_start=int(
            os.getenv("A2A_PORT_START", "9001")
        ),
    )


settings = get_settings()
