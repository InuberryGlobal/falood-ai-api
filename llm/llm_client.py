from typing import Optional, Dict, Any, List
import openai
import logging
import json
from pathlib import Path
from dataclasses import dataclass
import yaml
import backoff
from .prompt_builder import PromptBuilder, InterviewContext
import time
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    provider: str
    model: str
    temperature: float
    max_tokens: int
    top_p: float
    frequency_penalty: float
    presence_penalty: float
    api_key: str
    stream: bool = True
    max_history_messages: int = 5
    system_prompt_file: Optional[str] = None


def load_llm_config_from_yaml(path: str = "config/settings.yaml") -> LLMConfig:
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)["llm"]
            return LLMConfig(
                provider=data["provider"],
                model=data["model"],
                temperature=data.get("temperature", 0.7),
                max_tokens=data.get("max_tokens", 200),
                top_p=data.get("top_p", 1.0),
                frequency_penalty=data.get("frequency_penalty", 0.0),
                presence_penalty=data.get("presence_penalty", 0.0),
                api_key=os.getenv("OPENAI_API_KEY"),
                stream=True,
                max_history_messages=data.get("max_history_messages", 3),
                system_prompt_file=data.get("system_prompt_file")
            )
    except Exception as e:
        logger.error(f"Failed to load LLM config: {e}")
        raise


class LLMClient:
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or load_llm_config_from_yaml()
        self.prompt_builder = PromptBuilder()
        self.conversation_history: List[Dict[str, str]] = []

        if self.config.provider == "openai":
            openai.api_key = self.config.api_key
        else:
            raise NotImplementedError(f"Provider {self.config.provider} not supported.")

    @backoff.on_exception(backoff.expo, (openai.RateLimitError, openai.APIError, openai.APITimeoutError), max_tries=3, max_time=30)
    def generate_response(self, question: str, context: InterviewContext, on_token=None) -> str:
        prompt = self.prompt_builder.build_prompt(question, context)
        messages = self.conversation_history + [
            {"role": "system", "content": prompt},
            {"role": "user", "content": question}
        ]
        try:
            stream = openai.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                top_p=self.config.top_p,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty,
                stream=True
            )

            full_response = ""
            for chunk in stream:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    token = delta.content
                    full_response += token
                    if on_token:
                        on_token(token)

            self.conversation_history = messages + [{"role": "assistant", "content": full_response}]
            return full_response

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "[Error generating response]"