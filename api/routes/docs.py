"""Document upload and AI analysis endpoints."""
from fastapi import APIRouter, UploadFile, File, HTTPException
from core.ai.gemma_client import gemma
from core.ai.prompt_templates import PromptTemplate, render

router = APIRouter()


@router.post("/upload-and-analyze")
async def upload_and_analyze(file: UploadFile = File(...)):
    """Upload a text/document file and get AI analysis."""
    content = (await file.read()).decode("utf-8", errors="ignore")

    if len(content) < 10:
        raise HTTPException(status_code=422, detail="File too short or unreadable")

    summary = await gemma.generate(
        prompt=render(PromptTemplate.DOCUMENT_SUMMARIZE, text=content[:10000], max_words=300),
        temperature=0.3,
    )
    doc_type = await gemma.generate(
        prompt=render(PromptTemplate.CLASSIFY_DOCUMENT, text=content[:2000]),
        temperature=0.1,
    )

    return {
        "filename": file.filename,
        "word_count": len(content.split()),
        "classified_as": doc_type.strip(),
        "summary": summary,
    }
