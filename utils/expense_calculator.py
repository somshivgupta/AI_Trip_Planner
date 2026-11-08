import re

def to_float(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^\d.\-]", "", str(value))
    if not cleaned:
        raise ValueError(f"No numeric value in {value!r}")
    return float(cleaned)

class Calculator:
    @staticmethod
    def multiply(a: int, b: int) -> int:
        """
        Multiply two integers.

        Args:
            a: Numeric value only, e.g. 4000. No currency symbols or codes.
            b (int): The second integer.

        Returns:
            int: The product of a and b.
        """
        print(f"a={a}, type={type(a)}")
        print(f"b={b}, type={type(b)}")
        return to_float(a) * to_float(b)
    
    @staticmethod
    def calculate_total(numbers: list[float | str]) -> float:
        """
        Calculate the sum of a list of numbers.

        Args:
            numbers: List of numeric values only, e.g. [4000, 2500]. No currency symbols or codes.
        """
        return sum(to_float(n) for n in numbers)
    
    @staticmethod
    def calculate_daily_budget(total: float, days: int) -> float:
        """
        Calculate daily budget

        Args:
            total (float): Total cost.
            days (int): Total number of days

        Returns:
            float: Expense for a single day
        """
        return total / days if days > 0 else 0
    
    