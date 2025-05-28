from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

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
        "Réponds uniquement avec la traduction, séparée d'un séparateur de ligne, "
        "la langue réelle de la phrase à traduire en majuscules en anglais, "
        "suivie d'un autre séparateur de ligne, suivie d'une explication, "
        "suivie d'un autre séparateur de ligne, suivie de la version corrigée de la phrase s'il y a des fautes."
    )

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(OLLAMA_URL, json=payload)

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Ollama error")

    result = response.json()
    split_result = result["response"].split("\n\n")
    return {"translation": split_result[0], "language": split_result[1], "explanation": split_result[2], "correction": "" if len(split_result) < 4 else split_result[3]}

@app.post("/discuss")
async def discuss(req: DiscussionRequest):
    payload = {
        "model": MODEL_NAME,
        "prompt": req.text,
        "stream": False
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(OLLAMA_URL, json=payload)

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Ollama error")

    result = response.json()
    return {"response": result["response"]}