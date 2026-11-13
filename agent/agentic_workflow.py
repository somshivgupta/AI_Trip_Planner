from utils.model_loader import ModelLoader
from prompt_library.prompt import SYSTEM_PROMPT
from langgraph.graph import StateGraph, MessagesState, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from tools.weather_info_tool import WeatherInfoTool
from tools.place_search_tool import PlaceSearchTool
from tools.expense_calculator_tool import CalculatorTool
from tools.currency_conversion_tool import CurrencyConverterTool

import time

class GraphBuilder():
    def __init__(self, model_provider: str = "groq"):
        self.model_loader = ModelLoader(model_provider=model_provider)
        self.llm = self.model_loader.load_llm()

        self.tools = []

        self.weather_tools = WeatherInfoTool()
        self.place_search_tools = PlaceSearchTool()
        self.calculator_tools = CalculatorTool()
        self.currency_converter_tools = CurrencyConverterTool()

        self.tools.extend([* self.weather_tools.weather_tool_list,
        * self.place_search_tools.place_search_tool_list,
        * self.calculator_tools.calculator_tool_list,
        * self.currency_converter_tools.currency_converter_tool_list])

        self.llm_with_tools = self.llm.bind_tools(tools=self.tools)

        self.graph = None

        self.system_prompt=SYSTEM_PROMPT
    
    def agent_function(self, state: MessagesState):
        """Main agent function"""

        user_question = state["messages"]
        input_question = [self.system_prompt] + user_question

        start_time = time.perf_counter()

        try:
            response = self.llm_with_tools.invoke(input_question)

            llm_call_ms = (time.perf_counter() - start_time) * 1000

            print(
                f"event=llm_call_finished "
                f"llm_call_ms={llm_call_ms:.2f} "
                f"finish_reason={response.response_metadata.get('finish_reason')}"
            )

            return {"messages": [response]}

        except Exception:
            llm_call_ms = (time.perf_counter() - start_time) * 1000

            print(
                f"event=llm_call_failed "
                f"llm_call_ms={llm_call_ms:.2f}"
            )

            raise

    def build_graph(self, checkpointer=None):
        graph_builder = StateGraph(MessagesState)

        graph_builder.add_node("agent", self.agent_function)
        graph_builder.add_node("tools", ToolNode(tools=self.tools))

        graph_builder.add_edge(START, "agent")
        graph_builder.add_conditional_edges("agent", tools_condition)
        graph_builder.add_edge("tools", "agent")
        graph_builder.add_edge("agent", END)

        self.graph = graph_builder.compile(checkpointer=checkpointer)
        return self.graph


    def __call__(self, checkpointer=None):
        return self.build_graph(checkpointer=checkpointer)
