from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from agent.agentic_workflow import GraphBuilder
from langgraph.checkpoint.memory import InMemorySaver
from utils.timing import RequestMetrics, request_metrics

import logging
import time
import uuid
import os

from starlette.types import ASGIApp, Scope, Receive, Send, Message

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


class TimingMiddleware:

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send
    ):

        # Apply only to HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()

        request_id = str(uuid.uuid4())

        # Make request ID available to the endpoint
        scope.setdefault("state", {})["request_id"] = request_id

        status_code = None

        async def send_wrapper(message: Message):

            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]

            await send(message)

            # The final response body has been sent
            if (
                message["type"] == "http.response.body"
                and not message.get("more_body", False)
            ):
                total_request_ms = (
                    time.perf_counter() - start_time
                ) * 1000

                logger.info(
                    "event=http_request_finished "
                    "request_id=%s method=%s path=%s "
                    "status_code=%s total_request_ms=%.2f",
                    request_id,
                    scope["method"],
                    scope["path"],
                    status_code,
                    total_request_ms
                )

        await self.app(scope, receive, send_wrapper)

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

app.add_middleware(TimingMiddleware)
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
async def query_travel_agent(query: QueryRequest, request: Request):

    request_id = request.state.request_id

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

        # Create request-specific metrics
        metrics = RequestMetrics(request_id=request_id)
        metrics_token = request_metrics.set(metrics)

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

            logger.info(
                "event=agent_node_summary request_id=%s agent_node_count=%d",
                request_id,
                metrics.agent_node_count
            )

            request_metrics.reset(metrics_token)

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