import asyncio
import base64
import io
import json
import os
import re
import tempfile
import time
import wave
from datetime import datetime
from typing import Optional

import httptools
import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, UploadFile, File, Form
from kasa import Discover
from llama_index.core.agent.workflow import FunctionAgent, AgentInput
import magic

from pydantic import BaseModel
import httpx
from starlette.responses import StreamingResponse, JSONResponse
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec
from llama_index.llms.ollama import Ollama
from llama_index.core.agent.workflow import (
    FunctionAgent,
    ToolCall)
from llama_index.core.agent.workflow.workflow_events import (
    ToolCallResult,
)
from llama_index.core.workflow import Context
from starlette.websockets import WebSocketDisconnect
import soundfile as sf
from faster_whisper import WhisperModel
from api.higgs.api_routes import router as higgs_router
from api.models.discussion import DiscussionRequest

# Load faster-whisper model (only once)
model_size = "small"
asr_model = WhisperModel(model_size, compute_type="int8")

MODEL_NAME = "mistral-small:latest"  # ou mistral, gemma, etc.

app = FastAPI()

app.include_router(higgs_router)

mcp_client = BasicMCPClient("http://localhost:8000/sse")

mcp_tools = McpToolSpec(client=mcp_client)

SYSTEM_PROMPT = (
    "You are a helpful assistant. "
    "You must answer the user's questions, or perform the requested tasks."
    "You have access to the following tools:"
    " - weather: get the weather in a given location"
    " - time: get the current time"
    " - home_automation_toggle_device: toggle a device in the home automation system. Here are the available devices:"
    "   - salon"
    "   - chambre"
    ""
    "Json returned by agents and tools must be returned to the client as they are received."
)

llm = Ollama(model=MODEL_NAME, request_timeout=360.0)

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

@app.get("/turn_on_devices")
async def turn_on_devices():
    dev = await Discover.discover_single("192.168.1.40", username="natheitz.nh@gmail.com", password="Louneige07,")
    print(dev.mac)
    await dev.turn_on()
    await dev.update()

@app.get("/turn_off_devices")
async def turn_off_devices():
    dev = await Discover.discover_single("192.168.1.40", username="natheitz.nh@gmail.com", password="Louneige07,")
    await dev.turn_off()
    await dev.update()

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
                            "type": "final_response",
                            "content": content,
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
        async for event in run_agent_stream(req):
            yield f"{json.dumps(event)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)

def extract_json_from_tool_output_content(content_str: str):
    # Regex pour capturer le contenu entre text='...' qui contient du JSON
    match = re.search(r"text='({.*})'", content_str)
    if not match:
        raise ValueError("Impossible d'extraire le JSON de la chaîne content")

    json_str = match.group(1)
    return json.loads(json_str)
# Paramètres audio (doivent correspondre à ceux du client Ktor)
SAMPLE_RATE = 16000  # Hz
AUDIO_FORMAT = "PCM_16BIT" # Le client envoie du PCM 16-bit
CHANNELS = 1 # Mono

# Taille du segment audio à envoyer à Whisper pour transcription (en secondes)
# Un segment trop court peut réduire la précision, un trop long augmente la latence.
TRANSCRIPTION_SEGMENT_DURATION_SECONDS = 2.0
BYTES_PER_SAMPLE = 2 # 16-bit PCM = 2 bytes per sample
BYTES_PER_SECOND = SAMPLE_RATE * BYTES_PER_SAMPLE * CHANNELS
BUFFER_SIZE_FOR_TRANSCRIPTION = int(BYTES_PER_SECOND * TRANSCRIPTION_SEGMENT_DURATION_SECONDS)


async def run_agent_stream(req: DiscussionRequest):
    agent = await get_agent(mcp_tools)
    ctx = Context(agent)
    handler = agent.run(req.text, ctx=ctx)

    yield {'type': 'final_response', 'content': 'Thinking...\n'}

    async for event in handler.stream_events():
        if isinstance(event, ToolCallResult):
            try:
                tool_output_data = extract_json_from_tool_output_content(event.tool_output.content)
            except Exception as e:
                print(f"Erreur extraction JSON tool_output: {e}")
                tool_output_data = {"raw": event.tool_output.content}
            yield {'type': 'tool_result', 'tool_name': event.tool_name, 'tool_output': tool_output_data}

        elif isinstance(event, ToolCall):
            yield {'type': 'tool_call', 'tool_name': event.tool_name, 'tool_kwargs': event.tool_kwargs}

        await asyncio.sleep(0.01)

    final_response = await handler
    yield {'type': 'final_response', 'content': str(final_response)}


# Client HTTP asynchrone pour Ollama
ollama_client = httpx.AsyncClient(timeout=60.0)

@app.websocket("/ws/speak")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Connexion WebSocket acceptée.")

    audio_buffer = bytearray()  # Buffer pour accumuler les chunks audio
    processing_task = None  # Tâche pour le traitement asynchrone des chunks

    async def process_audio_buffer():
        nonlocal audio_buffer
        print(f"Audio buffer size: {len(audio_buffer)} bytes")
        print(f"First 10 bytes: {audio_buffer[:10]}")
        # Créer un fichier WAV temporaire à partir du buffer audio brut
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            tmp_path = tmp_wav.name
            with wave.open(tmp_wav, "wb") as wf:
                wf.setnchannels(1)          # mono
                wf.setsampwidth(2)          # 16-bit
                wf.setframerate(16000)      # 16kHz
                wf.writeframes(audio_buffer)

        audio_buffer = bytearray()  # Réinitialiser le buffer après extraction
        print(f"Audio buffer size: {len(audio_buffer)} bytes")
        print(f"First 10 bytes: {audio_buffer[:10]}")
        try:
            segments, _info = asr_model.transcribe(tmp_path, language="fr", beam_size=1)

            for segment in segments:
                transcription = segment.text.strip()
                print(f"Transcription: {transcription}")
                if transcription:
                    ask_req = DiscussionRequest(text=segment.text)
                    async for event in run_agent_stream(ask_req):
                        print("Event reçu dans WebSocket :", event)
                        await websocket.send_json(event)
                    await websocket.send_json({
                        "content": segment.text
                    })

                    # await websocket.send_json({
                    #     "response": extract_json_from_tool_output_content(response.content)
                    # })
        finally:
            print(f"WAV temp saved at: {tmp_path}")
            os.unlink(tmp_path)  # Nettoyer le fichier temporaire

    try:
        while True:
            # Réception d'un chunk audio
            audio_chunk = await websocket.receive_bytes()
            audio_buffer.extend(audio_chunk)

            # Déclencher traitement si le buffer atteint ~1s
            if len(audio_buffer) > 32000:  # 16000 samples/sec * 2 bytes/sample = ~32Ko
                if processing_task and not processing_task.done():
                    await processing_task
                processing_task = asyncio.create_task(process_audio_buffer())

    except WebSocketDisconnect:
        print("Connexion WebSocket déconnectée.")
    except Exception as e:
        print(f"Erreur WebSocket: {e}")
    finally:
        if processing_task:
            processing_task.cancel()
            try:
                await processing_task
            except asyncio.CancelledError:
                pass

        print("Fermeture de la connexion WebSocket.")

# Configuration
N8N_WEBHOOK_URL = "http://83.115.88.108:5678/webhook/claude-image-webhook"
#N8N_WEBHOOK_URL = "http://83.115.88.108:5678/webhook-test/claude-image-webhook"
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@app.post("/upload-image")
async def upload_image(
        file: UploadFile = File(...),
        message_text: Optional[str] = Form(""),
        source: Optional[str] = Form("FastAPI Upload")
):
    """
    Upload une image et l'envoie au webhook n8n

    - **file**: Fichier image à uploader
    - **message_text**: Texte accompagnant l'image (laisser vide pour "image seule")
    - **source**: Source du message (par défaut: "FastAPI Upload")
    """

    try:
        # Vérifier la taille du fichier
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Fichier trop volumineux. Maximum: {MAX_FILE_SIZE / 1024 / 1024}MB"
            )

        # Vérifier le type MIME
        mime_type = magic.from_buffer(content, mime=True)
        if mime_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Type de fichier non supporté. Types autorisés: {ALLOWED_IMAGE_TYPES}"
            )

        # Encoder l'image en base64
        base64_content = base64.b64encode(content).decode('utf-8')

        # Préparer les données pour n8n
        webhook_data = {
            "hasAttachment": True,
            "messageText": message_text.strip(),
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "attachments": [
                {
                    "filename": file.filename,
                    "content": base64_content,
                    "contentType": mime_type,
                    "size": len(content)
                }
            ]
        }

        # Envoyer au webhook n8n
        async with httpx.AsyncClient() as client:
            response = await client.post(
                N8N_WEBHOOK_URL,
                json=webhook_data,
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )

            if response.status_code == 200:
                return JSONResponse(
                    status_code=200,
                    content={
                        "success": True,
                        "message": "Image envoyée avec succès au webhook n8n",
                        "file_info": {
                            "filename": file.filename,
                            "size": len(content),
                            "mime_type": mime_type
                        },
                        "webhook_response": response.status_code,
                        "will_send_email": message_text.strip() == ""
                    }
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Erreur webhook n8n: {response.status_code} - {response.text}"
                )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Timeout lors de l'envoi au webhook n8n"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du traitement: {str(e)}"
        )