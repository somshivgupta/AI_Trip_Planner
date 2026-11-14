# Performance Optimization — Baseline Results

## 1. Objective

The objective of this baseline measurement is to understand the current performance of the AI Trip Planner before applying optimization techniques.

The measurements capture:
- Total HTTP request execution time.
- LangGraph execution time (`ainvoke`).
- Individual LLM call durations.
- Number of agent-node invocations.
- Input and output token usage.
- Individual tool execution times.

## 2. Test Environment

- **LLM Provider:** Groq
- **Model:** `openai/gpt-oss-120b`
- **Framework:** LangGraph
- **Backend:** FastAPI
- **Frontend:** Streamlit
- **Performance instrumentation:** Custom timing utility and request-level metrics.

## 3. Baseline Results

| Query | Total Request | Graph Execution | Agent Calls | Input Tokens | Output Tokens | Total Tokens |
|---|---:|---:|---:|---:|---:|---:|
| Goa — 5 days | 30.55 s | 30.52 s | 7 | 9,966 | 5,008 | 14,974 |
| Manali — 7 days | 168.89 s | 168.89 s | 5 | 28,435 | 5,488 | 33,923 |
| Bangkok — 5 days | 24.61 s | 24.61 s | 7 | 9,332 | 5,242 | 14,574 |

## 4. Observations

1. LLM calls account for a significant portion of the overall execution time.
2. Place-search tools generally take around 3–6 seconds.
3. Calculator tools execute very quickly, generally in less than 2 milliseconds.
4. Weather forecast retrieval takes approximately 100–400 milliseconds.
5. Groq rate-limit responses (HTTP 429) and retries significantly increase LLM execution time.
6. The Manali query took approximately 169 seconds, with multiple Groq 429 retries.

## 5. Test Limitations

- Only three successful queries were used for the baseline.
- The Manali query reused the same conversation thread as the Goa query, so its token usage includes conversation history.
- The Bangkok query ran in a different thread after the Streamlit application was refreshed.
- One Manali attempt failed with HTTP 413 because the requested token count exceeded the Groq TPM limit (8,000 tokens).
- One Bangkok attempt failed with HTTP 500; the exact cause was not established.
- These tests are useful for establishing an initial baseline but are not a fully controlled benchmark.
- Cache performance was not tested because caching has not yet been implemented.

## 6. Conclusion

The baseline measurements show that LLM execution and external place-search API calls are the major contributors to response time.

The next optimization steps will focus on asynchronous LLM execution, non-blocking HTTP requests, reuse of external search clients, and caching frequently requested data.

These measurements will be used to compare performance after optimization.