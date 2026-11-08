from langchain_core.tools import tool
from utils.model_loader import ModelLoader

@tool
def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b

llm = ModelLoader(model_provider="groq").load_llm()

llm_with_tools = llm.bind_tools([multiply])

response = llm_with_tools.invoke(
    "Calculate 120 multiplied by 30."
)

print("Content:", response.content)
print("Tool calls:", response.tool_calls)