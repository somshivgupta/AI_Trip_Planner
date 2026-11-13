from utils.expense_calculator import Calculator
from typing import List
from langchain.tools import tool

from utils.timing import measure_time

class CalculatorTool:
    def __init__(self):
        self.calculator = Calculator()
        self.calculator_tool_list = self._setup_tools()

    
    def _setup_tools(self) -> List:
        """Setup all tools for the calculator tool"""

        @tool
        def estimate_total_hotel_cost(
            price_per_night: float | str,
            total_days: float | str
        ) -> float:
            """Calculate total hotel cost. Numeric values only, no currency symbols or codes."""
            with measure_time("tool.estimate_total_hotel_cost"):
                return self.calculator.multiply(price_per_night, total_days)

        @tool
        def calculate_total_expense(costs: List[float | str]) -> float:
            """Calculate total expense of the trip from a list of costs. Numeric values only, e.g. [4000, 2500]."""
            with measure_time("tool.calculate_total_expense"):
                return self.calculator.calculate_total(costs)

        @tool
        def calculate_daily_expense_budget(
            total_cost: float | str,
            days: float | str
        ) -> float:
            """Calculate daily expense. Numeric values only, no currency symbols or codes."""
            with measure_time("tool.calculate_daily_expense_budget"):
                return self.calculator.calculate_daily_budget(total_cost, days)

        return [
            estimate_total_hotel_cost,
            calculate_total_expense,
            calculate_daily_expense_budget
        ]
