
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class TimingResult:
    name: str
    duration_ms: float


@dataclass
class RequestMetrics:
    request_id: str
    agent_node_count: int = 0


# Holds metrics for the current request
request_metrics: ContextVar[RequestMetrics | None] = ContextVar(
    "request_metrics",
    default=None
)


def record_agent_node_invocation():
    """Increment the agent-node count for the current request."""

    metrics = request_metrics.get()

    if metrics is None:
        return None

    metrics.agent_node_count += 1
    return metrics.agent_node_count


@contextmanager
def measure_time(name: str):
    start_time = time.perf_counter()

    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        print(f"[TIMING] {name}: {duration_ms:.2f} ms")
