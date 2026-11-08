import os
from dotenv import load_dotenv
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

from utils.config_loader import load_config

load_dotenv()


class ConfigLoader:
    def __init__(self):
        print("Loading config...")
        self.config = load_config()

    def __getitem__(self, key):
        return self.config[key]


class ModelLoader(BaseModel):
    model_provider: Literal["groq", "ollama"] = "groq"
    config: Optional[ConfigLoader] = Field(default=None, exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def model_post_init(self, __context: Any) -> None:
        self.config = ConfigLoader()

    def load_llm(self):
        print("LLM loading...")
        print(f"Loading model from provider: {self.model_provider}")

        if self.model_provider == "groq":
            print("Loading LLM from Groq...")

            groq_api_key = os.getenv("GROQ_API_KEY")

            if not groq_api_key:
                raise ValueError("GROQ_API_KEY is missing")

            model_name = self.config["llm"]["groq"]["model_name"]

            return ChatGroq(
                model=model_name,
                api_key=groq_api_key,
                temperature=0
            )

        elif self.model_provider == "ollama":
            print("Loading LLM from Ollama...")

            model_name = self.config["llm"]["ollama"]["model_name"]

            return ChatOllama(
                model=model_name,
                temperature=0
            )