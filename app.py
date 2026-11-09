from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from agent.agentic_workflow import GraphBuilder
from langgraph.checkpoint.memory import InMemorySaver

import os

load_dotenv()


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

    try:
        print(f"Received query: {query.question}")

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

        # Asynchronous graph execution
        output = await react_app.ainvoke(messages, config=config)

        if isinstance(output, dict) and "messages" in output:
            final_output = output["messages"][-1].content
        else:
            final_output = str(output)

        return {"answer": final_output}

    except Exception as e:
        print(f"Error processing query: {str(e)}")

        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )
