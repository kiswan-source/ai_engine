"""AI endpoints — chat, document analysis, structured output."""
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.ai.gemma_client import gemma
from core.ai.prompt_templates import (
    PromptTemplate, render,
    GEMMA_SYSTEM_MINING, GEMMA_SYSTEM_GENERAL,
)
from worker.ai.jobs_ai import enqueue_ai_job
from core.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


# ─── Schemas ──────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8192)
    system: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    stream: bool = False
    use_cache: bool = True


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=50_000)
    task: str = Field(
        default="summarize",
        description="summarize | extract_entities | classify | translate",
    )
    max_words: int = Field(default=300, ge=50, le=1000)


class JobRequest(BaseModel):
    prompt: str
    system: Optional[str] = None
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")


# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.get("/health")
async def ai_health():
    """Check Ollama + Gemma availability."""
    return await gemma.health_check()


@router.post("/chat")
async def chat(req: ChatRequest):
    """
    Direct Gemma chat — sync or streaming.
    Use stream=true for SSE token streaming.
    """
    system = req.system or GEMMA_SYSTEM_GENERAL

    if req.stream:
        async def token_generator():
            async for token in gemma.stream(req.message, system=system, temperature=req.temperature):
                yield token

        return StreamingResponse(token_generator(), media_type="text/plain")

    try:
        response = await gemma.generate(
            prompt=req.message,
            system=system,
            temperature=req.temperature,
            use_cache=req.use_cache,
        )
        return {"response": response, "model": gemma.model}
    except Exception as e:
        logger.error("Chat generation failed", error=str(e))
        raise HTTPException(status_code=503, detail=f"AI generation failed: {e}")


@router.post("/analyze")
async def analyze_document(req: AnalyzeRequest):
    """Analyze document text — summarize, extract entities, classify, or translate."""
    task_map = {
        "summarize": (PromptTemplate.DOCUMENT_SUMMARIZE, {"text": req.text, "max_words": req.max_words}),
        "extract_entities": (PromptTemplate.DOCUMENT_EXTRACT_ENTITIES, {"text": req.text}),
        "classify": (PromptTemplate.CLASSIFY_DOCUMENT, {"text": req.text[:2000]}),
        "translate": (PromptTemplate.TRANSLATE_TO_ENGLISH, {"text": req.text}),
    }

    if req.task not in task_map:
        raise HTTPException(status_code=400, detail=f"Unknown task: {req.task}")

    template, vars_ = task_map[req.task]
    prompt = render(template, **vars_)

    if req.task == "extract_entities":
        result = await gemma.generate_json(
            prompt=prompt,
            schema_hint='{"persons":[],"organizations":[],"locations":[],"dates":[],"numbers":[],"legal_refs":[]}',
        )
    else:
        result = await gemma.generate(prompt=prompt, temperature=0.3)

    return {"task": req.task, "result": result}


@router.post("/geological-summary")
async def geological_summary(data: dict):
    """Generate professional geological summary from raw data."""
    prompt = render(PromptTemplate.GEOLOGICAL_SUMMARY, data=str(data))
    result = await gemma.generate(prompt=prompt, system=GEMMA_SYSTEM_MINING, temperature=0.4)
    return {"summary": result}


@router.post("/jobs/enqueue")
async def enqueue_job(req: JobRequest):
    """Enqueue an AI job for async processing via RQ worker."""
    job_id = await enqueue_ai_job(
        prompt=req.prompt,
        system=req.system or GEMMA_SYSTEM_GENERAL,
        priority=req.priority,
    )
    return {"job_id": job_id, "status": "queued"}
