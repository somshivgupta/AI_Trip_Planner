import time
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class TimingResult:
    name: str
    duration_ms: float


@contextmanager
def measure_time(name: str):
    start_time = time.perf_counter()

    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        print(f"[TIMING] {name}: {duration_ms:.2f} ms")