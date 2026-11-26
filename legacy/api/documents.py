from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend import config
from backend.database.db import get_db
from backend.security.auth import require_admin, require_staff
from backend.services import document_service
from backend.services.rag_service import kb

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
def list_documents(user: dict = Depends(require_staff)):
    with get_db() as db:
        rows = db.execute(
            "SELECT id,title,department,service_id,source_url,version,review_date,status,synthetic,chunk_count,"
            "filename,created_at FROM documents ORDER BY (status='Active') DESC, id DESC").fetchall()
    return [dict(r) for r in rows]


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    department: str = Form(default=""),
    source_url: str = Form(default=""),
    version: str = Form(default=""),
    review_date: str = Form(default=""),
    user: dict = Depends(require_admin),
):
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    try:
        result = document_service.ingest(
            file.filename or "upload.txt", data, user["username"],
            {"title": title.strip(), "department": department.strip(), "source_url": source_url.strip(),
             "version": version.strip(), "review_date": review_date.strip(), "synthetic": "false"},
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    kb.rebuild()
    return result


@router.delete("/{doc_id}")
def delete_document(doc_id: int, user: dict = Depends(require_admin)):
    if not document_service.remove(doc_id, user["username"]):
        raise HTTPException(404, "Document not found.")
    kb.rebuild()
    return {"ok": True}
