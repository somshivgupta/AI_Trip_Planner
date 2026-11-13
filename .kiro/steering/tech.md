---
inclusion: always
---

# Tech Stack

## Runtime
- **Python** ≥ 3.11 (`.python-version` pins this)
- **Package manager:** `uv` (`pyproject.toml` uses `uv_build`)
- **Operative dependency list:** `requirements.txt` — the `pyproject.toml` dependencies are a
  stale scaffold and do not reflect the full set of installed packages

## Frameworks

| Layer               | Library                                              | Role                                              |
|---------------------|------------------------------------------------------|---------------------------------------------------|
| Backend API         | `FastAPI` + `uvicorn`                                | Async REST server (`app.py`)                      |
| Frontend            | `Streamlit`                                          | Browser UI (`streamlit_app.py`)                   |
| Agent orchestration | `LangGraph`                                          | ReAct graph with tool-calling loop and memory     |
| LLM / tool binding  | `LangChain` (`langchain`, `langchain-community`, `langchain-experimental`) | LLM abstraction, `@tool` decorators, messages |

## LLM Providers
Both are supported and selected via `model_provider` passed to `GraphBuilder`. The active default
in `app.py` is **Groq**.

| Provider        | Class                             | Model                  | Config key          | API key env var |
|-----------------|-----------------------------------|------------------------|---------------------|-----------------|
| Groq (default)  | `langchain_groq.ChatGroq`         | `openai/gpt-oss-120b`  | `llm.groq`          | `GROQ_API_KEY`  |
| Ollama (local)  | `langchain_ollama.ChatOllama`     | `llama3.2`             | `llm.ollama`        | none            |

Temperature is `0` for both providers.

## External APIs

| Service              | Purpose                                          | Library / Client                          | Env var                    |
|----------------------|--------------------------------------------------|-------------------------------------------|----------------------------|
| OpenWeatherMap       | Current weather + 10-step forecast               | `requests` (direct HTTP)                  | `OPENWEATHERMAP_API_KEY`   |
| Google Places API    | Attractions, restaurants, activities, transport  | `langchain_google_community.GooglePlacesTool` | `GPLACES_API_KEY`      |
| Tavily Search        | Automatic fallback when Google Places fails      | `langchain_tavily.TavilySearch`           | `TAVILY_API_KEY` (auto-read) |
| ExchangeRate-API v6  | Currency conversion on user request              | `requests` (direct HTTP)                  | `EXCHANGE_RATE_API_KEY`    |

All keys are loaded from `.env` via `python-dotenv`.

## Conversation Memory
Memory is implemented using LangGraph's built-in checkpointing mechanism:

- `app.py` creates a single `InMemorySaver` instance at application startup (inside the
  `lifespan` context manager) and passes it to `graph_builder(checkpointer=checkpointer)`
- The compiled graph is stored on `app.state.react_app` and reused across all requests
- Every `/query` call passes `{"configurable": {"thread_id": query.thread_id}}` as the LangGraph
  `config`, which routes the invocation to the correct per-thread message history
- `streamlit_app.py` generates one `uuid.uuid4()` per browser session, stored in
  `st.session_state.thread_id`, and includes it in every request payload
- Limitation: `InMemorySaver` is RAM-only — history does not persist across server restarts
  and does not scale across multiple worker processes

## Configuration
- `config/config.yaml` — LLM provider profiles (model names for groq and ollama)
- `utils/config_loader.py` — `load_config(path)` reads the YAML with `yaml.safe_load`;
  path is relative to the project root (must be launched from project root)
- `utils/model_loader.py` — `ModelLoader(BaseModel)` selects and instantiates the LLM;
  reads model name from config in `model_post_init`

## HTTP Communication
- Streamlit calls `requests.post("http://localhost:8000/query", json=payload)` synchronously
- FastAPI runs the graph with `await react_app.ainvoke(messages, config=config)` asynchronously
- Utility classes (`WeatherForecastTool`, `CurrencyConverter`) use the synchronous `requests`
  library internally, which blocks the asyncio event loop during tool execution

## Known Bugs
1. **Weather temperature units** (`tools/weather_info_tool.py`): `get_current_weather` does not
   pass `units=metric` to OpenWeatherMap, so temperature is in Kelvin despite the label saying "°C".
   `get_forecast_weather` correctly passes `units: metric`.
2. **Forecast condition check** (`tools/weather_info_tool.py` line 22): checks
   `if 'list' in 'forecast_data'` (string-in-string literal — always `True`) instead of
   `if forecast_data and 'list' in forecast_data`.
3. **Currency URL double-slash** (`utils/currency_converter.py`): `base_url` ends with `/latest/`
   and `.convert()` appends `/{from_currency}`, producing a double-slash URL.
4. **`raise` a string** (`streamlit_app.py`): `raise f"The response failed due to {e}"` raises a
   `TypeError` instead of surfacing the original error.
5. **Redundant graph edge** (`agent/agentic_workflow.py`): `add_edge("agent", END)` after
   `add_conditional_edges` is redundant — `tools_condition` already handles routing to `END`.
6. **CORS wildcard + credentials** (`app.py`): `allow_origins=["*"]` with
   `allow_credentials=True` is rejected by browsers per the CORS spec.
