from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from agent.agentic_workflow import GraphBuilder
from langgraph.checkpoint.memory import InMemorySaver

import logging
import time
import uuid
import os

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# Initialize resources during application startup
@asynccontextmanager
async def lifespan(app: FastAPI):

    print("Initializing Travel Agent Graph...")

    checkpointer = InMemorySaver()

    graph_builder = GraphBuilder(model_provider="groq")
    app.state.react_app = graph_builder(checkpointer=checkpointer)

    print("Travel Agent Graph initialized successfully!")

    yield

    # Application shutdown
    app.state.react_app = None
    print("Travel Agent Graph shut down.")


app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


class QueryRequest(BaseModel):
    question: str
    thread_id: str


@app.post("/query")
async def query_travel_agent(query: QueryRequest):

    request_id = str(uuid.uuid4())

    try:
        logger.info(
            "event=query_received request_id=%s thread_id=%s",
            request_id,
            query.thread_id
        )

        # Reuse the graph initialized during startup
        react_app = app.state.react_app

        messages = {
            "messages": [query.question]
        }

        config = {
            "configurable": {
                "thread_id": query.thread_id
            }
        }

        # Measure LangGraph execution time
        ainvoke_start = time.perf_counter()

        try:
            output = await react_app.ainvoke(messages, config=config)

        finally:
            ainvoke_ms = (time.perf_counter() - ainvoke_start) * 1000

            logger.info(
                "event=graph_ainvoke_finished request_id=%s "
                "thread_id=%s ainvoke_ms=%.2f",
                request_id,
                query.thread_id,
                ainvoke_ms
            )

        if isinstance(output, dict) and "messages" in output:
            final_output = output["messages"][-1].content
        else:
            final_output = str(output)

        logger.info(
            "event=query_completed request_id=%s thread_id=%s",
            request_id,
            query.thread_id
        )

        return {"answer": final_output}

    except Exception as e:

        logger.exception(
            "event=query_failed request_id=%s thread_id=%s",
            request_id,
            query.thread_id
        )

        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )