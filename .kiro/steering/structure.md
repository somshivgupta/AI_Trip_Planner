---
inclusion: always
---

# Project Structure

## Directory Layout
```
AI_Trip_Planner/
├── app.py                          # FastAPI backend — lifespan startup, /query endpoint, InMemorySaver
├── streamlit_app.py                # Streamlit frontend — form UI, UUID thread management, HTTP client
├── requirements.txt                # Operative dependency list (authoritative — use this)
├── pyproject.toml                  # Package metadata only — dependencies are a stale scaffold
├── .env                            # API keys (not committed)
├── config/
│   ├── config.yaml                 # LLM provider profiles: model names for groq and ollama
│   └── __init__.py                 # Empty
├── agent/
│   ├── agentic_workflow.py         # GraphBuilder — constructs and compiles the LangGraph ReAct graph
│   └── __init__.py                 # Empty
├── tools/                          # LangChain @tool wrappers (one class per domain)
│   ├── weather_info_tool.py        # WeatherInfoTool — get_current_weather, get_weather_forecast
│   ├── place_search_tool.py        # PlaceSearchTool — search_attractions, search_restaurants,
│   │                               #   search_activities, search_transportation
│   │                               #   (Google Places primary, Tavily automatic fallback)
│   ├── expense_calculator_tool.py  # CalculatorTool — estimate_total_hotel_cost,
│   │                               #   calculate_total_expense, calculate_daily_expense_budget
│   ├── currency_conversion_tool.py # CurrencyConverterTool — convert_currency
│   ├── arthamatic_op_tool.py       # UNUSED prototype — not imported anywhere
│   └── __init__.py                 # Empty
├── utils/                          # Raw service clients (no LangChain dependency)
│   ├── model_loader.py             # ModelLoader — config-driven ChatGroq / ChatOllama factory
│   ├── config_loader.py            # load_config() — reads config/config.yaml via yaml.safe_load
│   ├── weather_info.py             # WeatherForecastTool — HTTP client for OpenWeatherMap API
│   ├── place_info_search.py        # GooglePlaceSearchTool + TavilyPlaceSearchTool service classes
│   ├── expense_calculator.py       # Calculator class + to_float() helper
│   ├── currency_converter.py       # CurrencyConverter — HTTP client for ExchangeRate-API v6
│   └── save_to_document.py         # UNUSED — save_document() exports plan to Markdown file
├── prompt_library/
│   ├── prompt.py                   # SYSTEM_PROMPT (SystemMessage) — the sole system prompt
│   └── __init__.py                 # Empty
├── expection/
│   ├── expection_handling.py       # EMPTY placeholder — no exception classes defined
│   └── __init__.py                 # Empty
├── logger/
│   └── __init__.py                 # EMPTY placeholder — no logging configured
└── notebook/
    └── experiments.ipynb           # Development notebook
```

## Layered Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Streamlit Frontend  (streamlit_app.py)                  │
│  • UUID thread_id generated once per session             │
│  • Stored in st.session_state.thread_id                  │
│  • Sent with every POST /query request                   │
└──────────────────────┬──────────────────────────────────┘
                       │  HTTP POST localhost:8000/query
                       │  { question, thread_id }
┌──────────────────────▼──────────────────────────────────┐
│  FastAPI Backend  (app.py)                               │
│  • InMemorySaver created once at startup (lifespan)      │
│  • Compiled graph stored on app.state.react_app          │
│  • Passes thread_id as LangGraph configurable key        │
│  • await react_app.ainvoke(messages, config)             │
└──────────────────────┬──────────────────────────────────┘
                       │  LangGraph async invocation
┌──────────────────────▼──────────────────────────────────┐
│  LangGraph ReAct Agent  (agent/agentic_workflow.py)      │
│                                                          │
│   START → agent ──(tools_condition)──→ END              │
│               ↑           ↓                             │
│             tools ←───────┘                             │
│                                                          │
│  State:      MessagesState (append-only message list)    │
│  Memory:     InMemorySaver keyed by thread_id            │
│  System prompt prepended on every agent node invocation  │
└──────────────────────┬──────────────────────────────────┘
                       │  @tool function calls
┌──────────────────────▼──────────────────────────────────┐
│  Tools Layer  (tools/)                                   │
│                                                          │
│  WeatherInfoTool          PlaceSearchTool                │
│  • get_current_weather    • search_attractions           │
│  • get_weather_forecast   • search_restaurants           │
│                           • search_activities            │
│  CalculatorTool           • search_transportation        │
│  • estimate_total_        (Google Places → Tavily        │
│    hotel_cost               fallback on exception)       │
│  • calculate_total_                                      │
│    expense                CurrencyConverterTool          │
│  • calculate_daily_       • convert_currency             │
│    expense_budget                                        │
└──────────────────────┬──────────────────────────────────┘
                       │  service class calls
┌──────────────────────▼──────────────────────────────────┐
│  Utils / Services  (utils/)                              │
│  WeatherForecastTool   GooglePlaceSearchTool             │
│  TavilyPlaceSearchTool Calculator   CurrencyConverter    │
└──────────────────────┬──────────────────────────────────┘
                       │  HTTPS
     OpenWeatherMap · Google Places · Tavily · ExchangeRate-API
```

## Key Patterns

### Tool class pattern
Every active tool follows the same structure: a class holds a service instance and a
`_setup_tools()` method that defines `@tool`-decorated inner functions. The inner functions
capture `self` via closure. The resulting list is exposed as an instance attribute.

```python
class XTool:
    def __init__(self):
        self.service = XService(api_key)
        self.x_tool_list = self._setup_tools()

    def _setup_tools(self) -> List:
        @tool
        def do_x(param: str) -> str:
            """Docstring used by the LLM to decide when to call this tool."""
            return self.service.call(param)
        return [do_x]
```

### Google Places → Tavily fallback pattern
Each of the four `PlaceSearchTool` tools tries Google Places first. If Google raises any
exception (quota, auth, network), control falls through to Tavily automatically. The LLM
receives the result with a note indicating which provider responded.

```python
try:
    result = self.google_places_search.google_search_X(place)
    if result:
        return f"...as suggested by google: {result}"
except Exception as e:
    result = self.tavily_search.tavily_search_X(place)
    return f"Google cannot find the details due to {e}.\n...{result}"
```

### Config-driven model selection
The active LLM is chosen by passing `model_provider="groq"` (or `"ollama"`) to `GraphBuilder`.
Model names live in `config/config.yaml` — do not hardcode them in Python files.

### Memory / thread continuity
`InMemorySaver` is created once in `app.py`'s lifespan and shared across all requests via
`app.state`. Each request passes its `thread_id` through LangGraph's `configurable` config key.
LangGraph uses this to load and persist the per-thread message history automatically.

## Required Environment Variables
| Variable                  | Used by                              |
|---------------------------|--------------------------------------|
| `GROQ_API_KEY`            | `utils/model_loader.py`              |
| `OPENWEATHERMAP_API_KEY`  | `tools/weather_info_tool.py`         |
| `GPLACES_API_KEY`         | `tools/place_search_tool.py`         |
| `TAVILY_API_KEY`          | `tools/place_search_tool.py` (auto-read by LangChain) |
| `EXCHANGE_RATE_API_KEY`   | `tools/currency_conversion_tool.py`  |

## Dead Code (do not expand or reference)
| File                          | Status                                          |
|-------------------------------|-------------------------------------------------|
| `tools/arthamatic_op_tool.py` | Unused prototype — predates the class-based tool pattern |
| `expection/expection_handling.py` | Empty — no custom exception types defined  |
| `logger/__init__.py`          | Empty — no logging configured                   |
| `utils/save_to_document.py`   | Implemented but never called from app or frontend |
