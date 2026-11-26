from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.database.db import get_db, now_iso
from backend.services import ai_service, routing_service

router = APIRouter(prefix="/api", tags=["chat"])

LANGUAGE_NOTE = ("This prototype answers in English only. isiZulu, isiXhosa and Sesotho are planned; any "
                 "translation would need confirmation with the relevant department.")


class ChatIn(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    language: str = Field(default="en", max_length=5)


@router.post("/chat")
def chat(body: ChatIn):
    result = ai_service.answer_question(body.question.strip())
    topic = routing_service.classify(body.question)["category"] if result["status"] != "clarify" else None
    with get_db() as db:  # outcome + topic only; the question text is NOT stored
        db.execute("INSERT INTO chat_events(topic,outcome,timestamp) VALUES(?,?,?)",
                   (topic, result["status"], now_iso()))
    if body.language != "en":
        result["language_note"] = LANGUAGE_NOTE
    return result


@router.get("/services")
def services():
    return routing_service.public_services()
