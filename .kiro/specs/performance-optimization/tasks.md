# Implementation Plan: Performance and Response Optimization

## Overview

Incremental improvements to wall-clock latency and resource efficiency for the AI Trip Planner.
Task 1 must be completed first to establish a baseline. Tasks 2 and 3 can run in parallel.
Task 5 follows Tasks 3 and 4. Task 6 is always last.

## Baseline Measurement Protocol

Before starting any task beyond Task 1, run the following standardised queries against the
live system with only Task 1's timing instrumentation in place. Record all metrics in a local
notes file (not committed to the repo).

**Standard test queries:**
```
Q1: "Plan a 5-day trip to Goa"             # domestic popular
Q2: "Plan a 7-day trip to Manali"          # domestic mountain
Q3: "Plan a 5-day trip to Bangkok"         # international
Q4: Follow-up in same session as Q1:
    "What is the total budget for 3 days?"  # tests memory + calculator (not cache)
Q5: "Plan a 5-day trip to Goa"             # exact repeat of Q1 — cache-hit verification
                                            # run immediately after Q1 in the same session
```

**Metrics to record per query:**

| Metric | Source |
|--------|--------|
| `total_request_ms` | ASGI middleware wrapping the full send/receive cycle |
| `ainvoke_ms` | `timer` context manager in `app.py` around `ainvoke` |
| `llm_call_ms` per agent-node invocation | `time.perf_counter()` inside `agent_function` |
| `tool_duration_ms` per tool | timing log in each `@tool` function |
| `agent_node_calls` | per-request counter, initialised in endpoint handler |
| `input_tokens`, `output_tokens` | aggregated from all AIMessage `usage_metadata` after `ainvoke` |

> Q4 is a calculator follow-up — it does not exercise place or weather caches.
> Q5 is the dedicated cache-hit verification query. The 10ms cache-hit duration is a benchmark
> target; record actual results rather than assuming they will be met.

## Tasks

- [x] 1. Add Timing Instrumentation
  - Establish the baseline — no performance improvement is claimed from this task
  - **Files:** `utils/timing.py` (new), `app.py`, `tools/place_search_tool.py`, `tools/weather_info_tool.py`, `tools/currency_conversion_tool.py`, `tools/expense_calculator_tool.py`, `agent/agentic_workflow.py`
  - _Requirements: REQ-1_

  - [x] 1.1 Create `utils/timing.py` with an `async` context manager `timer(label, thread_id)` that logs elapsed milliseconds using Python's `logging` module at `INFO` level
    - _Requirements: REQ-1_

  - [x] 1.2 In `app.py`, configure basic logging (`logging.basicConfig`) and wrap the `await react_app.ainvoke(...)` call with `async with timer("ainvoke_ms", thread_id=...)`
    - _Requirements: REQ-1_

  - [ ] 1.3 In `app.py`, add ASGI middleware using `@app.middleware("http")` to measure `total_request_ms` using `time.perf_counter()` around `await call_next(request)` — this correctly includes response body serialisation that an endpoint-level timer misses; log as `[TIMING] path=<path> total_request_ms=<ms>`
    - _Requirements: REQ-1_

  - [ ] 1.4 In `agent_function` in `agent/agentic_workflow.py`, wrap the LLM call with `time.perf_counter()` before and after; log `[TIMING] llm_call_ms=<ms>` per invocation
    - _Requirements: REQ-1_

  - [ ] 1.5 In `app.py`, initialise a per-request `counters` dict (e.g. `{"agent_node_calls": 0}`) inside the endpoint handler — not as a module-level global — so concurrent requests do not share counter state; after `ainvoke` returns, log the final `agent_node_calls` value; coordinate the increment mechanism with `agent_function` (e.g. via `app.state` keyed by `thread_id`, or a context variable)
    - _Requirements: REQ-1_

  - [ ] 1.6 After `ainvoke` returns in `app.py`, iterate `output["messages"]` and sum `usage_metadata["input_tokens"]` and `usage_metadata["output_tokens"]` from all `AIMessage` objects that carry `usage_metadata` — `agent_function` is called multiple times per request and each produces one `AIMessage`; log the aggregated totals
    - _Requirements: REQ-1_

  - [x] 1.7 In each of the four `PlaceSearchTool` tool functions, record `time.perf_counter()` before and after the Google/Tavily call and log `[TIMING] tool=<name> place=<place> duration_ms=<ms>`
    - _Requirements: REQ-1_

  - [x] 1.8 In each of the two `WeatherInfoTool` tool functions, log duration similarly
    - _Requirements: REQ-1_

  - [ ] 1.9 In `tools/currency_conversion_tool.py`, add `time.perf_counter()` timing around the `convert_currency` tool function body; log `[TIMING] tool=convert_currency duration_ms=<ms>`
    - _Requirements: REQ-1_

  - [ ] 1.10 In `tools/expense_calculator_tool.py`, add `time.perf_counter()` timing around each of the three calculator tool functions; log `[TIMING] tool=<name> duration_ms=<ms>` — these are CPU-only but are instrumented to confirm negligible overhead
    - _Requirements: REQ-1_

  - [ ] 1.11 Run all five test queries; record baseline metrics in a local notes file (not committed to the repo); confirm `[TIMING]` lines appear for every tool category
    - _Requirements: REQ-1_

- [ ] 2. Async LLM Call and System Prompt Injection
  - Eliminate `run_in_executor` overhead for the LLM call (REQ-2) and ensure the system prompt is reliably the first message in LangGraph state across all turns (REQ-5)
  - **Files:** `agent/agentic_workflow.py`, `app.py`
  - _Requirements: REQ-2, REQ-5_

  - [ ] 2.1 Change `agent_function` signature from `def` to `async def`; replace `self.llm_with_tools.invoke(input_question)` with `await self.llm_with_tools.ainvoke(state["messages"])`; remove the `[self.system_prompt] +` local prepend entirely — the system prompt will be injected by `app.py` (see 2.2)
    - _Requirements: REQ-2, REQ-5_

  - [ ] 2.2 In `app.py`, before calling `ainvoke`, call `graph.get_state(config)` to check whether the thread has persisted messages; if `snapshot.values.get("messages")` is falsy (new thread), pass `{"messages": [SYSTEM_PROMPT, HumanMessage(query.question)]}`; if truthy (follow-up turn), pass `{"messages": [HumanMessage(query.question)]}` only — this ensures `SystemMessage` is persisted as index 0 by `InMemorySaver` after the first turn and is not re-injected on subsequent turns
    - _Requirements: REQ-5_

  - [ ] 2.3 Remove the redundant `graph_builder.add_edge("agent", END)` line from `build_graph`; this line is invalid alongside `add_conditional_edges` (Known Bug #5)
    - _Requirements: REQ-5, REQ-7_

  - [ ] 2.4 Verify the graph still compiles correctly (`graph_builder.compile()` succeeds) and run all five test queries; confirm: travel plans are correct and complete; Q4 follow-up receives a contextually appropriate response (memory intact); for a new thread `state["messages"][0]` is `SystemMessage` when `agent_function` runs; for a follow-up turn `state["messages"][0]` is still `SystemMessage` with no second `SystemMessage` in the history; `ainvoke_ms` is measured and recorded (a single-request reduction is not guaranteed — record the actual result)
    - _Requirements: REQ-2, REQ-5, REQ-7_

- [ ] 3. Async HTTP Clients
  - Replace synchronous `requests.get` with a shared `httpx.AsyncClient` per service class so HTTP I/O does not hold a thread pool slot during the wait (REQ-3); fix Bug #1 and Bug #3
  - **Files:** `utils/weather_info.py`, `utils/currency_converter.py`, `tools/weather_info_tool.py`, `tools/currency_conversion_tool.py`, `agent/agentic_workflow.py`, `app.py`
  - _Requirements: REQ-3_

  - [ ] 3.1 In `utils/weather_info.py`: remove `import requests`; add `import httpx`; in `__init__`, store `self.client = httpx.AsyncClient(timeout=10.0)` — do not create a new client inside any method; add `async def close(self)` calling `await self.client.aclose()`; convert `get_current_weather` and `get_forecast_weather` to `async def` using `response = await self.client.get(...)`; replace the status check with `response.raise_for_status()`; add `units=metric` to `get_current_weather` params (Bug #1 fix)
    - _Requirements: REQ-3_

  - [ ] 3.2 In `utils/currency_converter.py`: remove `import requests`; add `import httpx`; in `__init__`, store `self.client = httpx.AsyncClient(timeout=10.0)`; add `async def close(self)` calling `await self.client.aclose()`; fix double-slash URL by removing the trailing slash from `base_url` (Bug #3 fix); convert `convert` to `async def` using `response = await self.client.get(...)`; replace the status check with `response.raise_for_status()`
    - _Requirements: REQ-3_

  - [ ] 3.3 In `tools/weather_info_tool.py`: change `get_current_weather` and `get_weather_forecast` to `async def`; add `await` before each `self.weather_service` call
    - _Requirements: REQ-3_

  - [ ] 3.4 In `tools/currency_conversion_tool.py`: change `convert_currency` to `async def`; add `await` before `self.currency_service.convert(...)`
    - _Requirements: REQ-3_

  - [ ] 3.5 Add `GraphBuilder.close()` async method in `agent/agentic_workflow.py` calling `await self.weather_tools.weather_service.close()` and `await self.currency_converter_tools.currency_service.close()`; in `app.py` lifespan, store a reference to the `GraphBuilder` instance on `app.state` and call `await app.state.graph_builder.close()` in the shutdown section
    - _Requirements: REQ-3_

  - [ ] 3.6 Run all five test queries; confirm current weather returns temperature in Celsius, currency conversion returns correct amounts, no double-slash appears in the exchange-rate URL, and `tool_duration_ms` for weather and currency tools is measured and recorded
    - _Requirements: REQ-3, REQ-7_

- [ ] 4. Reuse `TavilySearch` Instance
  - Eliminate per-call object construction in the Tavily fallback path (REQ-4)
  - **Files:** `utils/place_info_search.py`
  - _Requirements: REQ-4_

  - [ ] 4.1 In `TavilyPlaceSearchTool.__init__`, add `self.tavily_tool = TavilySearch(topic="general", include_answer="advanced")`; replace the local `tavily_tool = TavilySearch(...)` construction in each of the four methods with `self.tavily_tool` — no threading lock is needed because `TavilySearch` holds only immutable state and each call builds its own local params dict (confirmed by source inspection)
    - _Requirements: REQ-4_

  - [ ] 4.2 Verify that the fallback path is exercised (temporarily break the Google key or mock an exception) and confirm the Tavily result is returned correctly
    - _Requirements: REQ-4, REQ-7_

- [ ] 5. TTL Cache for External API Responses
  - Avoid redundant API calls for repeat queries about the same destination (REQ-6); protect cache access with `threading.Lock` since `ToolNode` runs tools concurrently
  - **Files:** `tools/place_search_tool.py`, `tools/weather_info_tool.py`, `utils/currency_converter.py`, `requirements.txt`
  - _Requirements: REQ-6_

  - [ ] 5.1 Add `cachetools>=5.3.0` to `requirements.txt`
    - _Requirements: REQ-6_

  - [ ] 5.2 In `PlaceSearchTool.__init__`, add `self._place_cache = TTLCache(maxsize=128, ttl=3600)` and `self._cache_lock = threading.Lock()`; in each of the four tool functions, wrap both the cache read and write in `with self._cache_lock:` as a single critical section; use `(tool_name, place.lower())` as the cache key; log `[CACHE] HIT` or `[CACHE] MISS` at INFO level; note that locking prevents torn reads/writes but does not prevent two threads from both issuing an API call on a simultaneous first miss — this is acceptable
    - _Requirements: REQ-6_

  - [ ] 5.3 In `WeatherInfoTool.__init__`, add two separate caches: `self._current_weather_cache = TTLCache(maxsize=64, ttl=600)` and `self._forecast_cache = TTLCache(maxsize=64, ttl=1800)`, plus `self._cache_lock = threading.Lock()`; use `_current_weather_cache` in `get_current_weather` and `_forecast_cache` in `get_weather_forecast`, both keyed by `city.lower()`, both wrapped with `with self._cache_lock:`; two separate instances prevent key collisions for the same city name; log cache hit/miss
    - _Requirements: REQ-6_

  - [ ] 5.4 In `utils/currency_converter.py`, add `self._rate_cache = TTLCache(maxsize=32, ttl=3600)` and `self._cache_lock = threading.Lock()` to `CurrencyConverter.__init__`; in `convert`, normalise both `from_currency` and `to_currency` to uppercase before cache lookup and API call; cache `response.json()["conversion_rates"]` keyed by `from_currency.upper()`; on a cache hit, skip the HTTP call and compute `amount * cached_rates[to_currency.upper()]` directly; wrap reads and writes with `with self._cache_lock:`
    - _Requirements: REQ-6_

  - [ ] 5.5 Run the cache-hit verification test: call the same `@tool` function with identical arguments twice in the same process session (e.g. call `search_attractions("Goa")` twice directly, or run Q1 then Q5 in the same server session); confirm `[CACHE] HIT` appears on the second call; record actual `tool_duration_ms` — the 10ms target is a benchmark reference, not a guarantee
    - _Requirements: REQ-6, REQ-7_

- [ ] 6. Regression Verification
  - Confirm all optimisations are consistent with REQ-7 (preserve existing functionality)
  - _Requirements: REQ-7_

  - [ ] 6.1 Run all five test queries Q1–Q5 against the modified system; for each of Q1–Q3 verify: response is valid complete Markdown; contains day-by-day itinerary, hotel costs in INR, attractions, restaurants, activities, transport, cost breakdown, weather; dual itinerary (mainstream + off-beat) is present; all prices are in INR
    - _Requirements: REQ-7_

  - [ ] 6.2 Verify Q4 follow-up receives a contextually correct answer referencing the Q1 plan
    - _Requirements: REQ-7_

  - [ ] 6.3 Verify Q5 (repeat of Q1) shows `[CACHE] HIT` for place search and weather tools; record actual `tool_duration_ms` for cache hits
    - _Requirements: REQ-6, REQ-7_

  - [ ] 6.4 Confirm `InMemorySaver` memory still works: restart the server, run Q1 again, confirm a new plan is generated (old thread state is gone, as expected)
    - _Requirements: REQ-7_

  - [ ] 6.5 Record final metrics for all five queries and compare against baseline:

    | Metric | Baseline | Result | Notes |
    |--------|----------|--------|-------|
    | `total_request_ms` Q1–Q3 | (record baseline) | (record) | ASGI middleware |
    | `ainvoke_ms` Q1–Q3 | (record baseline) | (record) | improvement not guaranteed |
    | `llm_call_ms` per agent node | (record baseline) | (record) | |
    | `agent_node_calls` Q1–Q3 | (record baseline) | (record) | expect 3–5 |
    | `input_tokens` per request Q1–Q3 | (record baseline) | (record) | no reduction expected |
    | `tool_duration_ms` cache hit Q5 | N/A | (record) | benchmark target < 10ms |
    | `ainvoke_ms` Q5 vs Q1 | N/A | (record) | cache hit benefit |
    | `requests` import in weather/currency utils | Present | Absent | |

    - _Requirements: REQ-1, REQ-2, REQ-3, REQ-5, REQ-6_

## Notes

- Task 1 must run first; baseline data is required to validate all other tasks
- Tasks 2 and 3 touch different files and can be worked on simultaneously
- Task 4 should precede Task 5 to keep `utils/place_info_search.py` stable before caching is layered on
- Q4 is a calculator follow-up — it does not exercise place or weather caches
- Q5 is the dedicated cache-hit verification query; the 10ms target is a benchmark, not a guarantee
- The `inject_system_prompt` node approach is not used: `MessagesState`'s `add_messages` reducer always appends, so a node cannot reliably place `SystemMessage` before the existing `HumanMessage`; `app.py` uses `graph.get_state()` instead
- `ainvoke_ms` improvement is not promised — network jitter dominates single-request measurements; record and compare actual results
- Bug #2 (forecast condition string check), Bug #4 (`raise f"..."`), and Bug #6 (CORS) remain out of scope

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2", "3", "4"] },
    { "id": 2, "tasks": ["5"] },
    { "id": 3, "tasks": ["6"] }
  ]
}
```
