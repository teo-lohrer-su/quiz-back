from fastapi import FastAPI, HTTPException, Depends 
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import uuid
from datetime import datetime
from .security import verify_api_key

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_pages = {}  # {page_id: {current_question: None, answers: [], ...}}


class Option(BaseModel):
    text: str
    is_correct: bool


class Question(BaseModel):
    text: str
    options: List[Option]


class Page(BaseModel):
    title: str
    description: str


class StudentAnswer(BaseModel):
    option_index: int


@app.post("/api/pages/", response_model=dict)
async def create_page(page: Page, api_key: str = Depends(verify_api_key)):
    page_id = str(uuid.uuid4())
    active_pages[page_id] = {
        "title": page.title,
        "description": page.description,
        "current_question": None,
        "answers": [],
        "created_at": datetime.now().isoformat(),
    }
    return {"page_id": page_id}


@app.get("/api/pages/{page_id}")
async def get_page_status(page_id: str):
    if page_id not in active_pages:
        raise HTTPException(status_code=404, detail="Page not found")

    # Don't expose correct answers to students
    page_data = active_pages[page_id].copy()
    if page_data["current_question"]:
        sanitized_question = page_data["current_question"].copy()
        sanitized_question["options"] = [
            {"text": opt["text"]} for opt in sanitized_question["options"]
        ]
        page_data["current_question"] = sanitized_question

    return page_data


@app.post("/api/pages/{page_id}/questions")
async def post_question(
    page_id: str, question: Question, api_key: str = Depends(verify_api_key)
):
    if page_id not in active_pages:
        raise HTTPException(status_code=404, detail="Page not found")

    # Validate that at least one option is marked as correct
    if not any(opt.is_correct for opt in question.options):
        raise HTTPException(
            status_code=400, detail="At least one option must be marked as correct"
        )

    question_data = {
        "text": question.text,
        "options": [
            {"text": opt.text, "is_correct": opt.is_correct} for opt in question.options
        ],
        "created_at": datetime.now().isoformat(),
        "active": True,
    }

    active_pages[page_id]["current_question"] = question_data
    active_pages[page_id]["answers"] = []

    return {"status": "success"}


@app.post("/api/pages/{page_id}/answers")
async def post_answer(page_id: str, answer: StudentAnswer):
    if page_id not in active_pages:
        raise HTTPException(status_code=404, detail="Page not found")

    page = active_pages[page_id]
    if not page["current_question"] or not page["current_question"]["active"]:
        raise HTTPException(status_code=400, detail="No active question")

    if answer.option_index >= len(page["current_question"]["options"]):
        raise HTTPException(status_code=400, detail="Invalid option index")

    # Record the answer
    answer_data = {
        "option_index": answer.option_index,
        "timestamp": datetime.now().isoformat(),
        "is_correct": page["current_question"]["options"][answer.option_index][
            "is_correct"
        ],
    }
    page["answers"].append(answer_data)

    return {"status": "success"}


@app.post("/api/pages/{page_id}/close-question")
async def close_question(page_id: str, api_key: str = Depends(verify_api_key)):
    if page_id not in active_pages:
        raise HTTPException(status_code=404, detail="Page not found")

    page = active_pages[page_id]
    if not page["current_question"]:
        raise HTTPException(status_code=400, detail="No active question")

    page["current_question"]["active"] = False

    # Calculate statistics
    total_answers = len(page["answers"])
    correct_answers = sum(1 for ans in page["answers"] if ans["is_correct"])

    option_stats = {}
    for i, _ in enumerate(page["current_question"]["options"]):
        option_stats[i] = {
            "count": sum(1 for ans in page["answers"] if ans["option_index"] == i),
            "is_correct": page["current_question"]["options"][i]["is_correct"],
        }

    stats = {
        "total_answers": total_answers,
        "correct_answers": correct_answers,
        "correct_percentage": (correct_answers / total_answers * 100)
        if total_answers > 0
        else 0,
        "option_stats": {
            i: {
                "count": stats["count"],
                "percentage": (stats["count"] / total_answers * 100)
                if total_answers > 0
                else 0,
                "is_correct": stats["is_correct"],
            }
            for i, stats in option_stats.items()
        },
    }

    return stats

# @app.post("/api/revoke/{token_id}")
# async def revoke_token(
#     token_id: str,
#     key_data: dict = Depends(verify_api_key)  # Only allow revocation by valid token holders
# ):
#     REVOKED_TOKENS.add(token_id)
#     return {"status": "success", "message": f"Token {token_id} has been revoked"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
