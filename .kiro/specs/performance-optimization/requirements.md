# Requirements Document

## Introduction

This spec targets measurable improvements to the response time and resource efficiency of the
AI Trip Planner. The agent calls multiple external APIs and an LLM over several reasoning steps
to produce a single travel plan. The goal is to reduce wall-clock latency for the end user
without altering any visible product behaviour.

All bottlenecks are grounded in direct inspection of the installed source code. No bottleneck
is assumed without a code or library reference. This spec is consistent with the steering files
in `.kiro/steering/` (product.md, tech.md, structure.md), which are the authoritative
description of the existing implementation.

---

## Confirmed Findings from Code Inspection

### Finding 1 — LLM call in `agent_function` is synchronous

**File:** `agent/agentic_workflow.py`
**Evidence:**
```python
def agent_function(self, state: MessagesState):
    user_question = state["messages"]
    input_question = [self.system_prompt] + user_question
    response = self.llm_with_tools.invoke(input_question)   # sync call
    return {"messages": [response]}
```
`invoke` is the synchronous LangChain method. Because `agent_function` is a plain `def`,
LangGraph dispatches it via `run_in_executor` when the graph is called with `ainvoke`, occupying
a thread pool slot for the full LLM round-trip. `ChatGroq` has a native async path
(`_agenerate` / `async_client`) confirmed by inspection of the installed `langchain_groq`
source. Switching to `async def agent_function` with `await self.llm_with_tools.ainvoke(...)`
routes the call through that native async path, eliminating the thread hop.

### Finding 2 — `ToolNode` already dispatches multiple tool calls in parallel

**File:** installed `langgraph.prebuilt.tool_node` (confirmed from venv source)
**Evidence:**
```python
# ToolNode._afunc
coros = []
for call, tool_runtime in zip(tool_calls, tool_runtimes):
    coros.append(self._arun_one(call, input_type, tool_runtime))
outputs = await asyncio.gather(*coros)
```
`_execute_tool_async` calls `await tool.ainvoke(...)`. For sync `@tool` functions,
`BaseTool._arun` falls back to:
```python
return await run_in_executor(None, self._run, *args, **kwargs)
```
**Conclusion:** When the graph is invoked with `ainvoke`, `ToolNode` already dispatches all
tool calls in a single batch in parallel via `asyncio.gather`. Each sync tool runs concurrently
in separate worker threads, not on the event loop. The `requests.get` calls in weather and
currency utilities block those worker threads (not the asyncio event loop itself); replacing
them with `httpx.AsyncClient` and `async def` tools lets the tool await I/O without occupying
a thread slot during the wait.

### Finding 3 — `WeatherForecastTool` and `CurrencyConverter` use synchronous `requests`

**Files:** `utils/weather_info.py`, `utils/currency_converter.py`
**Evidence (confirmed in tech.md "HTTP Communication" section):**
> "Utility classes (`WeatherForecastTool`, `CurrencyConverter`) use the synchronous `requests`
> library internally, which blocks the asyncio event loop during tool execution."

Specific lines:
- `utils/weather_info.py`: `response = requests.get(url, params=params)`
- `utils/currency_converter.py`: `response = requests.get(url)`

`httpx` is already listed in `requirements.txt` — no new dependency is required.

This rewrite also resolves two known bugs documented in tech.md:
- **Known Bug #1** (`get_current_weather` temperature in Kelvin): add `units=metric` to the
  `get_current_weather` params in `utils/weather_info.py` during the rewrite.
- **Known Bug #3** (double-slash URL in `utils/currency_converter.py`): the URL construction
  is corrected as part of replacing the HTTP client.

### Finding 4 — Each Tavily fallback call instantiates a new `TavilySearch` object

**File:** `utils/place_info_search.py`
**Evidence:** All four methods in `TavilyPlaceSearchTool`:
```python
def tavily_search_attractions(self, place: str):
    tavily_tool = TavilySearch(topic="general", include_answer="advanced")  # new every call
    result = tavily_tool.invoke(...)
```
Object construction on every invocation is unnecessary. Inspection of the installed
`langchain_tavily` source confirms `TavilySearch` and `TavilySearchAPIWrapper` hold only
immutable state (API key, optional base URL). No mutable state is modified during invocation —
each call builds its own local params dict independently. A single shared instance in `__init__`
is therefore safe, and no threading lock is required.

### Finding 5 — System prompt sent to the LLM on every agent node invocation

**File:** `agent/agentic_workflow.py`
**Evidence** (also noted in tech.md "Layered Architecture" diagram):
> "System prompt prepended on every agent node invocation"

```python
input_question = [self.system_prompt] + user_question   # every invocation
```
The `SYSTEM_PROMPT` is approximately 250 tokens. The agent node executes 3–5 times per
typical trip query. This is unavoidable with the current approach and is **not** a correctness
problem — it is the standard LangChain pattern for prepending a system prompt.

The key state-management concern is that the system prompt is currently prepended to a local
variable and never written into LangGraph state. This means `InMemorySaver` does not persist
the `SystemMessage` across turns. The `add_messages` reducer used by `MessagesState` appends
messages — returning `{"messages": [SystemMessage]}` from any node when the state already
contains the user's `HumanMessage` would place the `SystemMessage` **after** the
`HumanMessage`, not before it. A dedicated `inject_system_prompt` node cannot reliably ensure
the `SystemMessage` is first in the LangGraph message list.

The correct approach for this architecture is to have `app.py` check thread history via
`graph.get_state(config)` before each `ainvoke` call. On the first call for a thread, it
passes `[SYSTEM_PROMPT, HumanMessage(question)]`; on follow-up calls it passes only
`[HumanMessage(question)]`. The `SystemMessage` is then persisted in `InMemorySaver` at index 0
after the first turn, and `agent_function` can remove its local prepend entirely — subsequent
turns see it already at the front of `state["messages"]`. This correctly scopes system prompt
injection without requiring graph topology changes.

**Token count implication:** Persisting the `SystemMessage` in state means it is included in
the full message history passed to `ainvoke` on every agent-node call within a request — the
same as the current local-prepend behaviour. This change does not reduce the number of tokens
sent to the LLM per agent-node invocation. The benefit is correct state management (the system
prompt is reliably first in the history) and consistency across conversation turns.

### Finding 6 — No timing or observability instrumentation exists

**Files:** `app.py`, all tool files, `logger/__init__.py`
**Evidence:** `app.py` contains two `print()` calls at startup. `logger/__init__.py` is an
empty placeholder (confirmed in structure.md "Dead Code" table). No measurement of request
duration, per-tool latency, LLM latency, or token counts exists anywhere in the codebase.
Without a baseline, no improvement can be objectively validated.

---

## Requirements

### REQ-1: Establish a timing baseline before any other change

The system must emit structured timing logs covering: total HTTP request duration (via ASGI
middleware, which wraps the full send/receive cycle including response serialisation), LangGraph
`ainvoke` duration, per-call LLM duration inside `agent_function`, agent node invocation count,
per-tool execution duration for all tool categories (place search, weather, currency,
calculator), and aggregated LLM token usage across all agent-node invocations per request.

This instrumentation must be in place and baseline data collected **before** any other
requirement in this spec is implemented.

**Files to change:** `utils/timing.py` (new), `app.py`, `tools/place_search_tool.py`,
`tools/weather_info_tool.py`, `tools/currency_conversion_tool.py`,
`tools/expense_calculator_tool.py`, `agent/agentic_workflow.py`

**Acceptance criteria:**
- `[TIMING]` log lines appear in FastAPI stdout for every `/query` request
- Each line includes: label, `thread_id` where applicable, and duration in milliseconds
- `total_request_ms` is measured by ASGI middleware that wraps the full request/response cycle,
  including response body serialisation — an endpoint-level `perf_counter` only covers handler
  execution, not the streaming send of the response body
- `ainvoke_ms` is measured by the `timer` async context manager inside the endpoint handler
- `llm_call_ms` is measured inside `agent_function` around each `ainvoke` call and logged
  separately per invocation
- `agent_node_calls` counter is per-request; it must be initialised per invocation of the
  `/query` endpoint (not as a module-level or instance-level global) to remain correct under
  concurrent requests; the final count is logged after `ainvoke` completes
- LLM token usage (`input_tokens`, `output_tokens`) is **aggregated** across all AIMessage
  responses generated during a single request — `agent_function` is called multiple times per
  request and each call returns one AIMessage with its own `usage_metadata`; in `app.py`,
  iterate `output["messages"]` after `ainvoke` and sum `usage_metadata` from all AIMessages
  that carry it
- Per-tool duration is logged in all four tool categories:
  place search (all four tools), weather (both tools), currency conversion, and all three
  calculator tools
- Baseline metrics for the five standard test queries are recorded before Task 2 begins

---

### REQ-2: Convert LLM call to async

`agent_function` in `agent/agentic_workflow.py` must be declared `async def` and call
`await self.llm_with_tools.ainvoke(...)` so the LLM uses `ChatGroq`'s native async HTTP path
rather than a thread pool slot.

**File to change:** `agent/agentic_workflow.py`

**Acceptance criteria:**
- `agent_function` is `async def`
- `ainvoke` is used instead of `invoke`
- LangGraph compiles and runs the graph without error
- Travel plan output is identical in format and content to baseline
- Conversation memory (InMemorySaver + thread_id) works correctly across follow-up queries
- `ainvoke_ms` is measured and reported; a single-request reduction versus baseline is not
  guaranteed (network jitter dominates) but results must be recorded for comparison

---

### REQ-3: Replace synchronous `requests` with `httpx.AsyncClient` in HTTP utility classes

`utils/weather_info.py` and `utils/currency_converter.py` must use a single
`httpx.AsyncClient` instance per service class, created in `__init__` with an explicit
`timeout=10.0` seconds and reused across all calls. Both files' methods must be declared
`async def`. The corresponding tool wrapper functions in `tools/weather_info_tool.py` and
`tools/currency_conversion_tool.py` must also be declared `async def` with `await` on
service calls.

Each utility class must implement `async def close(self)` that calls `await self.client.aclose()`.
`GraphBuilder` must expose a `close()` coroutine that calls `close()` on each owned service
instance. `app.py`'s lifespan shutdown section must `await` that method to release connections.

`response.raise_for_status()` replaces the manual status code check in both utility classes.

No new dependency is introduced — `httpx` is already in `requirements.txt`.

As part of this rewrite, the following known bugs from tech.md must also be fixed:
- **Bug #1:** Add `units=metric` to the `get_current_weather` params in `utils/weather_info.py`
  so temperature is returned in Celsius, not Kelvin.
- **Bug #3:** Fix the double-slash URL in `utils/currency_converter.py` by ensuring
  `base_url` does not end with a trailing slash before `/{from_currency}` is appended.

**Files to change:** `utils/weather_info.py`, `utils/currency_converter.py`,
`tools/weather_info_tool.py`, `tools/currency_conversion_tool.py`, `agent/agentic_workflow.py`,
`app.py`

**Acceptance criteria:**
- `import requests` is absent from both utility files
- A single `httpx.AsyncClient(timeout=10.0)` instance is created in `__init__` and reused
  across all calls in both utility classes — a new `AsyncClient` is not created inside any
  method
- Each utility class implements `async def close(self)` that calls `await self.client.aclose()`
- `GraphBuilder.close()` calls close on each owned service instance; `app.py` lifespan calls
  `await` on the result during shutdown
- `response.raise_for_status()` is used in both utility classes
- `get_current_weather` returns temperature in Celsius (`units=metric` applied)
- Currency converter URL contains no double slash
- All tool outputs match the expected format
- No `TypeError` or `RuntimeError` from async/await mismatch

---

### REQ-4: Reuse `TavilySearch` instance across calls

`TavilyPlaceSearchTool` in `utils/place_info_search.py` must instantiate `TavilySearch`
once in `__init__` and reuse that instance in all four search methods.

Sharing a single `TavilySearch` instance is safe because inspection of the installed
`langchain_tavily` source confirms `TavilySearch` and `TavilySearchAPIWrapper` hold only
immutable state (API key, optional base URL). No mutable state is modified during invocation —
each call builds its own local params dict. No threading lock is needed.

**File to change:** `utils/place_info_search.py`

**Acceptance criteria:**
- `TavilySearch` is constructed exactly once per `TavilyPlaceSearchTool` instance
- All four methods reference `self.tavily_tool` instead of a local variable
- Tavily fallback results are unchanged when Google Places raises an exception

---

### REQ-5: Inject system prompt once per conversation thread via `app.py`

`app.py` must check thread history before each `ainvoke` call and include the `SYSTEM_PROMPT`
`SystemMessage` only on a thread's first request. This guarantees the `SystemMessage` is
persisted as the first message in `InMemorySaver` state and is correctly positioned in the
message history on all subsequent turns.

**Mechanism:** Before calling `ainvoke`, `app.py` calls `graph.get_state(config)` to check
whether the thread already has persisted messages. If the state is empty (new thread), it
passes `[SYSTEM_PROMPT, HumanMessage(question)]` to `ainvoke`. If the state has existing
messages (follow-up turn), it passes only `[HumanMessage(question)]`. After the first turn,
`InMemorySaver` persists `[SystemMessage, HumanMessage, AIMessage, ...]` and the
`SystemMessage` remains at index 0 for all subsequent turns.

`agent_function` must remove its local `[self.system_prompt] +` prepend entirely and use
`state["messages"]` directly — the system prompt is already present in the state on all turns.

**Why not an `inject_system_prompt` node:** The `MessagesState` `add_messages` reducer always
appends to the existing list. When the first node runs, the user's `HumanMessage` is already
in state (LangGraph merges the `ainvoke` input before dispatching the first node). Returning
`{"messages": [SystemMessage]}` from a node at that point appends the `SystemMessage` **after**
the `HumanMessage`, placing it out of order. Using `RemoveMessage` to delete and re-add the
user message produces the same result due to the reducer's processing order. The `get_state`
approach in `app.py` avoids the reducer entirely by injecting the `SystemMessage` before the
first `ainvoke` call, while the reducer then correctly appends subsequent turns.

**Token count implication:** This change does not reduce the number of tokens sent to the LLM
per agent-node invocation. The full accumulated message history — including the persisted
`SystemMessage` — is passed to `ainvoke` on every agent-node call within a request, the same
as before. The benefit is correct and predictable state management: the system prompt is
reliably at index 0, and it does not appear more than once in the history regardless of how
many agent-node steps the graph takes.

**Files to change:** `app.py`, `agent/agentic_workflow.py`

**Acceptance criteria:**
- `app.py` calls `graph.get_state(config)` before `ainvoke` and conditionally prepends
  `SYSTEM_PROMPT` only when `snapshot.values.get("messages")` is falsy
- `agent_function` does not prepend `self.system_prompt` to the message list locally
- For a new thread: `state["messages"][0]` is a `SystemMessage` when `agent_function` runs
- For a follow-up turn on the same thread: `state["messages"][0]` is still `SystemMessage`;
  no second `SystemMessage` is present in the history
- A new thread correctly receives the system prompt on its first call
- An existing thread correctly passes the existing history (with `SystemMessage` first) on
  follow-up calls without re-injecting the prompt
- The redundant `graph_builder.add_edge("agent", END)` line (Known Bug #5) must be removed
  from `build_graph` as a correctness fix; it was already invalid alongside
  `add_conditional_edges` per the LangGraph documentation

---

### REQ-6: Add short-lived TTL cache for external API responses

Place search results, weather data, and currency exchange rates must be cached with TTLs
appropriate to how frequently the data changes. The cache must be transparent to the
LangGraph agent — tool function signatures and return formats are unchanged.

`cachetools` is added to `requirements.txt` as the only new dependency introduced by this spec.

**Thread safety:** `ToolNode` dispatches tool calls concurrently via `asyncio.gather` with
`run_in_executor`, so tool functions may run in different threads simultaneously.
`cachetools.TTLCache` is not thread-safe. A `threading.Lock` per cache owner must wrap every
read-then-write operation. Note that locking the read and write as a single critical section
prevents torn reads and writes but does **not** prevent duplicate external calls during
simultaneous first misses for the same key — two threads can both read a miss and both issue
the API call. This is acceptable for this workload (extra API calls are rare and harmless), and
a more complex double-checked locking pattern is not required.

**Cache keys and TTLs:**

| Data | Cache location | Cache key | TTL |
|------|---------------|-----------|-----|
| Place search (all 4 tools) | `PlaceSearchTool` instance | `(tool_name, place.lower())` | 3600s |
| Current weather | `WeatherInfoTool._current_weather_cache` | `city.lower()` | 600s |
| Weather forecast | `WeatherInfoTool._forecast_cache` | `city.lower()` | 1800s |
| Currency exchange rates | `CurrencyConverter._rate_cache` | `from_currency.upper()` | 3600s |

Weather uses **two separate `TTLCache` instances** — `_current_weather_cache` (600s) and
`_forecast_cache` (1800s) — to prevent key collisions between current-weather and forecast
lookups for the same city name.

For currency: both `from_currency` and `to_currency` are normalised to uppercase before
cache lookup and before the HTTP call. The full `conversion_rates` dict
(`response.json()["conversion_rates"]`) is cached keyed by `from_currency.upper()`. On a cache
hit, the HTTP call is skipped and the result is computed as
`amount * cached_rates[to_currency.upper()]`.

**Files to change:** `tools/place_search_tool.py`, `tools/weather_info_tool.py`,
`utils/currency_converter.py`, `requirements.txt`

**Acceptance criteria:**
- `[CACHE] HIT` log line appears for a repeat query to the same destination within the TTL
- `tool_duration_ms` for a cache hit is typically under 10ms (this is a benchmark target;
  actual results depend on lock contention and logging overhead — results must be recorded,
  not assumed)
- A repeat query returns the same data as the original API response
- After TTL expiry (or server restart), a cache miss triggers a normal API call
- `cachetools>=5.3.0` is present in `requirements.txt`
- `WeatherInfoTool` holds two separate `TTLCache` instances (`_current_weather_cache` and
  `_forecast_cache`) with TTLs of 600s and 1800s respectively
- Every cache read-and-write pair is wrapped in `with self._cache_lock:` using a
  `threading.Lock` owned by the same class
- Both `from_currency` and `to_currency` are uppercased before cache key construction and
  before passing to the exchange rate lookup
- The cache-hit verification test calls the same tool function with identical arguments twice
  in the same session (not relying on conversational routing); `[CACHE] HIT` must appear on
  the second call

---

### REQ-7: Preserve all existing functionality

Every change made under this spec must leave the following product behaviours exactly as they
are today:

- Dual itinerary output (mainstream tourist + off-beat alternatives)
- All prices presented in INR by default
- Currency conversion tool invoked only on explicit user request
- Conversation memory: `InMemorySaver` + `thread_id` continuity within a session
- Google Places as primary / Tavily as automatic fallback for all four place search tools
- All 10 tool functions present with identical names and input/output signatures
- `config/config.yaml`-driven model selection (model names never hardcoded)
- `/query` endpoint request/response contract unchanged

The following known bugs from tech.md are explicitly in scope or out of scope:
- **Bug #1** (temperature in Kelvin) — **in scope**, fixed in Task 3 as part of the httpx rewrite
- **Bug #3** (double-slash URL) — **in scope**, fixed in Task 3 as part of the httpx rewrite
- **Bug #5** (redundant `add_edge`) — **in scope**, removed in Task 2 as part of the graph restructure
- **Bug #2** (forecast condition string check) — out of scope
- **Bug #4** (`raise f"..."` in `streamlit_app.py`) — out of scope
- **Bug #6** (CORS wildcard + credentials in `app.py`) — out of scope

---

## Out of Scope

- **Response streaming** — requires changes to the FastAPI endpoint (SSE/WebSocket) and
  Streamlit frontend rendering. This is a separate architectural feature.
- **Persistent checkpointing** — replacing `InMemorySaver` with a database-backed checkpointer
  is a reliability and scalability concern, not a latency improvement.
- **LLM provider or model changes** — Groq already provides a native async path and is among
  the fastest inference providers available. Provider selection is a product decision.
- **Streamlit frontend async** — `streamlit_app.py` runs in a single-user synchronous context.
  The `requests.post` call is acceptable for the current deployment model.
- **Multi-worker scaling** — horizontal scaling is an infrastructure concern outside the
  scope of single-process response time improvement.
- **Dead-code cleanup** — `tools/arthamatic_op_tool.py`, `expection/`, `logger/__init__.py`,
  and `utils/save_to_document.py` are listed as dead code in structure.md and must not be
  modified or expanded as part of this spec.
