import asyncio
import json
import time

import httptools
from fastapi import FastAPI, HTTPException
from llama_index.core.agent.workflow import FunctionAgent
from pydantic import BaseModel
import httpx
from starlette.responses import StreamingResponse
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec
from llama_index.llms.ollama import Ollama
from llama_index.core.agent.workflow import (
    FunctionAgent,
    ToolCallResult,
    ToolCall)

from llama_index.core.workflow import Context

MODEL_NAME = "mistral-small:latest"  # ou mistral, gemma, etc.

app = FastAPI()

mcp_client = BasicMCPClient("http://localhost:8000/sse")

mcp_tools = McpToolSpec(client=mcp_client)

SYSTEM_PROMPT = (
    "You are a helpful assistant. "
    "You must answer the user's questions."
    "You have access to the following tools:"
    " - weather: get the weather in a given location"
    " - time: get the current time"
)

llm = Ollama(model=MODEL_NAME, request_timeout=120.0)


async def get_agent(tools: McpToolSpec):
    tools = await tools.to_tool_list_async()
    return FunctionAgent(
        name="Agent",
        description="An agent that can do everything",
        tools=tools,
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
    )

async def get_tools():
    tools = await mcp_tools.to_tool_list_async()
    for tool in tools:
        print(tool.metadata.name, tool.metadata.description)

@app.on_event("startup")
async def startup_event():
    await get_tools()

OLLAMA_URL = "http://localhost:11434/api/generate"

class TranslationRequest(BaseModel):
    source_lang: str
    target_lang: str
    text: str

class DiscussionRequest(BaseModel):
    text: str

@app.post("/translate")
async def translate(req: TranslationRequest):
    prompt = (
        f"Traduis en '{req.target_lang}' la phrase en '{req.source_lang}' : \"{req.text}\".\n"
        "Réponds uniquement avec la traduction, suivi du séparateur de ligne suivant : |||, "
        f"suivie en '{req.source_lang}' de la langue réelle de la phrase à traduire en majuscules suivie du séparateur de ligne suivant : |||, "
        f"suivie d'une explication en '{req.source_lang}', suivie du séparateur de ligne suivant : |||, "
        f"suivie de la version corrigée de la phrase s'il y a des fautes en '{req.source_lang}'."
    )

    async def event_stream():
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": True
        }

        numbreOfSeparationsCounter = 0
        breaklineContainer = ""
        result = {
            "translation": "",
            "language": None,
            "explanation": None,
            "correction": None
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", OLLAMA_URL, json=payload) as response:
                async for line in response.aiter_lines():
                    try:
                        data = json.loads(line)
                        content = data.get("response", "")

                        tmpContent = content

                        print(f"LINE: {content}")

                        hasBreakline = False

                        tmpContent = tmpContent.replace(" ", "").replace("\n", "")
                        print(f"REPLACED CONTENT: {tmpContent}")
                        if "|" in tmpContent:
                            hasBreakline = True
                            breaklineContainer += tmpContent

                        if hasBreakline and breaklineContainer.strip() is not "|||":
                            print(f"BREAKLINE CONTAINER: {breaklineContainer}")
                            continue
                        elif hasBreakline:
                            content = content.replace("|", "")

                        if "|||" in breaklineContainer:
                            numbreOfSeparationsCounter += 1
                            breaklineContainer = ""
                            result = {
                                "translation": "",
                                "language": None,
                                "explanation": None,
                                "correction": None
                            }

                        # Traitement selon compteur
                        if numbreOfSeparationsCounter == 0:
                            result["translation"] = content
                        elif numbreOfSeparationsCounter == 1:
                            result["language"] = content
                        elif numbreOfSeparationsCounter == 2:
                            result["explanation"] = content
                        elif numbreOfSeparationsCounter == 3:
                            result["correction"] = content

                        print(f"RESULT: {result}")

                        yield f"{json.dumps(result)}\n\n"

                        await asyncio.sleep(0.01)  # Ajout explicite pour laisser la boucle rescheduler


                    except Exception as e:
                        print("Erreur parsing:", e)
                        continue

    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream",
        "X-Accel-Buffering": "no",  # Pour nginx reverse proxy
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)

@app.post("/discuss")
async def discuss(req: DiscussionRequest):
    payload = {
        "model": MODEL_NAME,
        "prompt": req.text,
        "stream": True
    }

    async def event_stream():
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", OLLAMA_URL, json=payload) as response:
                async for line in response.aiter_lines():
                    try:
                        data = json.loads(line)
                        content = data.get("response", "")
                        result = {
                            "response": content,
                        }
                        print("Response:", result)
                        yield f"{json.dumps(result)}\n\n"
                        await asyncio.sleep(0.01)  # Ajout explicite pour laisser la boucle rescheduler

                    except Exception as e:
                        print("Erreur parsing:", e)
                        continue

    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream",
        "X-Accel-Buffering": "no",  # Pour nginx reverse proxy
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)

@app.post("/ask")
async def ask(req: DiscussionRequest):
    async def event_stream():
        # get the agent
        agent = await get_agent(mcp_tools)

        # create the agent context
        agent_context = Context(agent)

        handler = agent.run(req.text, ctx=agent_context)

        yield f"data: {json.dumps({'type': 'final_response', 'content': 'Thinking...'})}\n\n"

        # Stream agent events
        async for event in handler.stream_events():
            if isinstance(event, ToolCall):
                yield f"data: {json.dumps({'type': 'tool_call', 'tool_name': event.tool_name, 'tool_kwargs': event.tool_kwargs})}\n\n"
            elif isinstance(event, ToolCallResult):
                yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': event.tool_name, 'tool_output': str(event.tool_output)})}\n\n"
            # Add other event types from LlamaIndex workflow if you want to stream more details
            # For example, if there's an event for LLM response chunks, you'd handle it here.
            # LlamaIndex's agent stream_events primarily focuses on tool interactions.
            # To stream the final LLM response from the agent, we'll need to get it at the end.
            await asyncio.sleep(0.01) # Small delay to allow event loop to breathe

        # After all events, get the final response from the agent
        final_response = await handler
        yield f"data: {json.dumps({'type': 'final_response', 'content': str(final_response)})}\n\n"


    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream",
        "X-Accel-Buffering": "no",  # For nginx reverse proxy
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


async def handle_user_message(
    message_content: str,
    agent: FunctionAgent,
    agent_context: Context,
    verbose: bool = False,
):
    handler = agent.run(message_content, ctx=agent_context)
    async for event in handler.stream_events():
        if verbose and type(event) == ToolCall:
            print(f"Calling tool {event.tool_name} with kwargs {event.tool_kwargs}")
        elif verbose and type(event) == ToolCallResult:
            print(f"Tool {event.tool_name} returned {event.tool_output}")

    response = await handler
    return str(response)