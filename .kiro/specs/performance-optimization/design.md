# Performance and Response Optimization — Technical Design

## Overview

This design describes internal changes to the AI Trip Planner to improve response latency and
resource efficiency. No new user-visible features are introduced. The two-process architecture
(Streamlit → FastAPI → LangGraph → Tools → Utils → APIs) is preserved in full — no layers are
added or removed and the `/query` API contract is unchanged.

The changes address six confirmed bottlenecks identified by direct code inspection: missing
observability, synchronous LLM dispatch, synchronous HTTP in utility classes, per-call Tavily
object construction, system prompt misplaced in every agent-node invocation, and absent caching
for external API responses.

## Architecture

The existing architecture is preserved. Changes are highlighted below:

```
Streamlit (unchanged)
  → FastAPI /query
      ASGI timing middleware (new)                     ← REQ-1
      get_state() system-prompt check (new)            ← REQ-5
      → LangGraph ainvoke
          agent node  →  async LLM call (ainvoke)      ← REQ-2
          tools node  →  asyncio.gather + run_in_executor (unchanged)
                          search_*       (sync, Tavily reused)      ← REQ-4
                          get_weather_*  (async def, httpx client)  ← REQ-3
                          convert_*      (async def, httpx client)  ← REQ-3
                          estimate/calculate/* (sync, unchanged)
```

Place-search tools remain synchronous `def` functions. They are already dispatched in parallel
by `ToolNode`'s `asyncio.gather` + `run_in_executor` mechanism and do not benefit from being
declared `async def` without also making `GooglePlacesTool.run()` and `TavilySearch.invoke()`
async, which would require changes to third-party LangChain internals.

`requests.get` in weather and currency utility classes blocks worker threads (not the asyncio
event loop) while awaiting HTTP responses. Replacing them with a shared `httpx.AsyncClient` and
`async def` tools lets those calls yield to the event loop instead of occupying a thread slot.

## Components and Interfaces

### `utils/timing.py` (new)

```python
class timer:
    """Async context manager that logs elapsed time at INFO level."""
    def __init__(self, label: str, thread_id: str = ""): ...
    async def __aenter__(self) -> "timer": ...
    async def __aexit__(self, *_) -> None: ...
```

Logger name: `trip_planner.timing`. Log format: `[TIMING] thread=<id> <label>=<ms>ms`.

### `app.py` — ASGI middleware (new)

```python
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info("[TIMING] path=%s total_request_ms=%.1f", request.url.path, elapsed_ms)
    return response
```

An endpoint-level `perf_counter` only covers handler execution and does not include the time
spent streaming the response body. ASGI middleware wraps the full request/response cycle.

### `app.py` — system prompt injection (modified)

```python
snapshot = app.state.react_app.get_state(config)
has_history = bool(snapshot.values.get("messages"))
if has_history:
    messages = {"messages": [HumanMessage(content=query.question)]}
else:
    messages = {"messages": [SYSTEM_PROMPT, HumanMessage(content=query.question)]}
```

`GraphBuilder.close()` is called in the lifespan shutdown to release the shared
`httpx.AsyncClient` connections owned by the utility classes.

### `agent/agentic_workflow.py` — `agent_function` (modified)

```python
async def agent_function(self, state: MessagesState):
    start = time.perf_counter()
    response = await self.llm_with_tools.ainvoke(state["messages"])
    llm_ms = (time.perf_counter() - start) * 1000
    logger.info("[TIMING] llm_call_ms=%.1fms", llm_ms)
    return {"messages": [response]}
```

The local `[self.system_prompt] +` prepend is removed. The `SystemMessage` arrives in
`state["messages"]` already (injected by `app.py` on the first turn). The redundant
`add_edge("agent", END)` is removed from `build_graph`.

### `utils/weather_info.py` — `WeatherForecastTool` (modified)

```python
class WeatherForecastTool:
    def __init__(self, api_key: str):
        self.client = httpx.AsyncClient(timeout=10.0)   # single shared instance
    async def close(self): await self.client.aclose()
    async def get_current_weather(self, place: str) -> dict: ...
    async def get_forecast_weather(self, place: str) -> dict: ...
```

A new `AsyncClient` is not created inside any method. `response.raise_for_status()` replaces
the manual status code check. `units=metric` is added to `get_current_weather` (Bug #1 fix).

### `utils/currency_converter.py` — `CurrencyConverter` (modified)

```python
class CurrencyConverter:
    def __init__(self, api_key: str):
        self.base_url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest"  # no trailing slash
        self.client = httpx.AsyncClient(timeout=10.0)
        self._rate_cache = TTLCache(maxsize=32, ttl=3600)
        self._cache_lock = threading.Lock()
    async def close(self): await self.client.aclose()
    async def convert(self, amount: float, from_currency: str, to_currency: str) -> float: ...
```

URL corrected (no double slash — Bug #3 fix). Both `from_currency` and `to_currency` are
normalised to uppercase before cache lookup and API call.

### `utils/place_info_search.py` — `TavilyPlaceSearchTool` (modified)

```python
class TavilyPlaceSearchTool:
    def __init__(self):
        self.tavily_tool = TavilySearch(topic="general", include_answer="advanced")
    # all four methods use self.tavily_tool instead of constructing a new instance
```

No threading lock is required: `TavilySearch` holds only immutable state and each call builds
a local params dict independently (confirmed by source inspection of installed package).

### TTL cache pattern (applied to `PlaceSearchTool` and `WeatherInfoTool`)

```python
self._place_cache = TTLCache(maxsize=128, ttl=3600)
self._cache_lock = threading.Lock()

# In each tool function:
cache_key = ("attractions", place.lower())
with self._cache_lock:
    if cache_key in self._place_cache:
        logger.info("[CACHE] HIT ...")
        return self._place_cache[cache_key]
# ... API call ...
with self._cache_lock:
    self._place_cache[cache_key] = result
```

Locking the read-then-write as a single critical section prevents torn reads and writes. It
does not prevent duplicate API calls when two threads simultaneously miss the same key — both
will proceed to call the API, and one result overwrites the other. This is acceptable for this
workload.

`WeatherInfoTool` uses two separate `TTLCache` instances (`_current_weather_cache` TTL 600s,
`_forecast_cache` TTL 1800s) to prevent key collisions between current-weather and forecast
lookups for the same city name.

## Data Models

No new data models are introduced. All changes are internal to existing classes.

The `MessagesState` schema (`Annotated[list[AnyMessage], add_messages]`) is unchanged. The
`add_messages` reducer always appends new messages to the existing list. This reducer behaviour
is why a dedicated `inject_system_prompt` node cannot reliably ensure `SystemMessage` is first
— by the time any node runs, the user's `HumanMessage` is already in state, and returning
`{"messages": [SystemMessage]}` from a node appends it after the existing message. The
`app.py` `get_state()` approach injects the `SystemMessage` before the first `ainvoke` call,
circumventing the reducer ordering constraint entirely.

**Token count note:** Persisting the `SystemMessage` in LangGraph state means it travels with
the full message history. The number of tokens sent to the LLM per agent-node invocation is
unchanged from the current behaviour — the full history (including `SystemMessage`) is passed
on every call. This change provides correct state ordering, not token savings.

## Correctness Properties

Property 1: System prompt appears exactly once in the message history for any thread, regardless of turn count. **Validates: Requirements 5**

Property 2: No second SystemMessage is added to an existing thread on follow-up calls — the app.py get_state() check prevents re-injection. **Validates: Requirements 5**

Property 3: TTL cache entries expire after their configured TTL; a cache miss after expiry triggers a fresh API call without stale data being served. **Validates: Requirements 6**

Property 4: Cache reads and writes for the same cache object are always wrapped in with self._cache_lock; concurrent threads cannot observe a partially-written cache entry. **Validates: Requirements 6**

Property 5: httpx.AsyncClient instances are closed during application shutdown via GraphBuilder.close(); no connection handles are leaked between server restarts. **Validates: Requirements 3**

Property 6: agent_node_calls counter is initialised per request inside the endpoint handler; concurrent requests do not share counter state. **Validates: Requirements 1**

## Error Handling

- `httpx.AsyncClient` calls use `response.raise_for_status()` — HTTP 4xx/5xx responses raise `httpx.HTTPStatusError` which propagates to the tool function and is handled by LangGraph's tool error mechanism
- `httpx.AsyncClient` is configured with `timeout=10.0` seconds — requests that exceed this raise `httpx.TimeoutException`
- TTL cache misses fall through to the existing API call path; cache failures (unexpected) are not silently swallowed
- The `graph.get_state(config)` call in `app.py` uses the existing checkpointer; if it raises, the error propagates to the standard 500 error handler

## Testing Strategy

**Cache-hit verification (deterministic):** Call the same `@tool` function with identical arguments twice in the same process session. The second call must log `[CACHE] HIT`. This is more reliable than relying on conversational routing, which depends on LLM tool-call decisions.

**System prompt ordering (new thread):** Call `graph.invoke` with a fresh `thread_id`. After the call, inspect `graph.get_state(config).values["messages"][0]` and assert it is a `SystemMessage`.

**System prompt ordering (follow-up):** Call `graph.invoke` twice with the same `thread_id`. After the second call, assert that exactly one `SystemMessage` appears in `graph.get_state(config).values["messages"]`.

**Async HTTP:** Assert `import requests` is not present in `utils/weather_info.py` or `utils/currency_converter.py` after Task 3 is complete.

**Regression:** All five standard test queries must return valid complete Markdown travel plans with dual itineraries, INR prices, weather, and cost breakdowns.
