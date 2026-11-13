---
inclusion: always
---

# Product: AI Trip Planner

## Purpose
AI Trip Planner is a conversational travel planning assistant that accepts natural-language queries
(e.g. "Plan a 5-day trip to Goa") and returns a comprehensive, fully formatted travel plan in a
single response. It targets an Indian audience and always presents prices in Indian Rupees (₹ / INR).

## Core Features

### Trip Planning
- **Dual itinerary** — always produces two plans: one for mainstream tourist spots and one for
  off-beat alternatives nearby
- **Day-by-day itinerary** — structured schedule across the full trip duration
- **Hotel recommendations** — suggested accommodation with approximate per-night cost in INR
- **Attractions, restaurants, activities, transportation** — discovered in real time via Google
  Places API (with Tavily as automatic fallback)

### Cost Planning
- **Itemised cost breakdown** — hotel, food, activities, transport listed separately
- **Total trip cost** — computed from the itemised list, not estimated as a lump sum
- **Daily budget** — total divided by number of days
- **Currency conversion** — available on explicit user request to show costs in another currency

### Live Data
- **Weather** — current conditions and short forecast for the destination at time of query
- **Place information** — real-time data from Google Places; Tavily used automatically when
  Google Places raises an exception

### Conversation Memory
- Each browser session generates a UUID `thread_id` stored in Streamlit session state
- The `thread_id` is sent with every request and used as the LangGraph checkpointer key
- The `InMemorySaver` checkpointer retains the full message history for the lifetime of the
  server process, enabling natural follow-up questions within the same session
  (e.g. "What about hotels under ₹3000?" after an initial plan)

## Behavioural Rules (enforced via system prompt)
- All prices are in INR by default; currency conversion tool is only called when the user
  explicitly requests another currency
- Numbers passed to calculation tools must be plain floats — no currency symbols or strings
- Totals in the output must be derived from itemised costs so the budget is internally consistent
- Output is always formatted in clean Markdown in a single comprehensive response

## Target Audience
Indian travellers planning domestic or international trips. All cost estimates use realistic
Indian market prices.

## Entry Points
| Interface   | File                | Default URL                   |
|-------------|---------------------|-------------------------------|
| Browser UI  | `streamlit_app.py`  | `http://localhost:8501`       |
| REST API    | `app.py`            | `http://localhost:8000/query` |

## API Contract
```json
POST /query
{ "question": "Plan a trip to Manali for 7 days", "thread_id": "<uuid>" }

→ 200 OK
{ "answer": "<markdown-formatted travel plan>" }

→ 500 Internal Server Error
{ "error": "<exception message>" }
