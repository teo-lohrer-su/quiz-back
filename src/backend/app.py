from fastapi import FastAPI, HTTPException, Depends 
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
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
    html: Optional[str] = None  # Allow HTML content for rich markdown


class Question(BaseModel):
    text: str
    options: List[Option]
    allow_multiple: bool = False  # For multiple choice questions
    html: Optional[str] = None  # Allow HTML content for the question


class Page(BaseModel):
    title: str
    description: str


class StudentAnswer(BaseModel):
    option_indices: List[int]  # List of selected options


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
            {"text": opt["text"], "html": opt.get("html")} for opt in sanitized_question["options"]
        ]
        # Include the allow_multiple flag and HTML content
        print(f"page_data: {page_data}")
        print(f"allow multiple: {page_data['current_question'].get('allow_multiple', False)}")
        sanitized_question["allow_multiple"] = page_data["current_question"].get("allow_multiple", False)
        if "html" in page_data["current_question"]:
            sanitized_question["html"] = page_data["current_question"]["html"]
        
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
            {
                "text": opt.text, 
                "is_correct": opt.is_correct,
                **({"html": opt.html} if opt.html else {})
            } 
            for opt in question.options
        ],
        "allow_multiple": question.allow_multiple or len([opt for opt in question.options if opt.is_correct]) > 1,
        "created_at": datetime.now().isoformat(),
        "active": True,
    }
    print(f"POST allow multiple: {question.allow_multiple}")
    print(f"POST question_data: {question}")
    # question_data["allow_multiple"] = len([opt for opt in question.options if opt.is_correct]) > 1
    
    # Add HTML content if provided
    if question.html:
        question_data["html"] = question.html

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

    # Validate that option indices are valid
    num_options = len(page["current_question"]["options"])
    for idx in answer.option_indices:
        if idx < 0 or idx >= num_options:
            raise HTTPException(status_code=400, detail=f"Invalid option index: {idx}")

    # If not a multiple choice question, validate that only one option is selected
    if not page["current_question"].get("allow_multiple", False) and len(answer.option_indices) > 1:
        raise HTTPException(status_code=400, detail="Multiple selections not allowed for this question")
    
    # Calculate if the answer is correct based on selected options
    # For multiple choice: all correct options must be selected and no incorrect ones
    if page["current_question"].get("allow_multiple", False):
        # Get all indices for correct options
        correct_indices = [
            i for i, opt in enumerate(page["current_question"]["options"]) 
            if opt["is_correct"]
        ]
        # Check if selected options match exactly with correct options
        is_correct = set(answer.option_indices) == set(correct_indices)
    else:
        # For single choice, just check if the selected option is correct
        is_correct = page["current_question"]["options"][answer.option_indices[0]]["is_correct"] if answer.option_indices else False

    # Record the answer
    answer_data = {
        "option_indices": answer.option_indices,
        "timestamp": datetime.now().isoformat(),
        "is_correct": is_correct,
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

    # Calculate option selection statistics
    option_stats = {}
    for i, _ in enumerate(page["current_question"]["options"]):
        # Count how many times each option was selected
        count = sum(1 for ans in page["answers"] if i in ans["option_indices"])
        option_stats[i] = {
            "count": count,
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
        "is_multiple_choice": page["current_question"].get("allow_multiple", False)
    }

    return stats


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)