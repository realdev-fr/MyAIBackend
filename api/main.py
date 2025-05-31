import asyncio
import json
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from starlette.responses import StreamingResponse

app = FastAPI()

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral-small:latest"  # ou mistral, gemma, etc.

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