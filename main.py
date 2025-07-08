from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl
from models import User, QuizQuestion, UserAnswer
from database import get_db, store_mcq_questions, store_user_answers, get_user_by_username, get_quiz_questions_by_user, store_recommended_courses
from user_management import user_login, user_register
from quiz_generator import generate_mcq_questions, parse_mcqs, evaluate
from course_recommender import generate_course_recommendations
import asyncio
from database import setup_database
from dotenv import load_dotenv
load_dotenv()

import shutil
import os
from datetime import datetime
import json
import cohere

import fitz  # PyMuPDF

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import SessionLocal
from models import ResumeUpload, Employee
from models import ResumeUpload, ResumeText  # ✅ import your new model
from utils.csv_validator import validate_hr_csv
from utils.pii_scrubber import scrub_pii
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import User, QuizQuestion, UserAnswer  # Make sure these are imported

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Only allow your React app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response data
class UserProfile(BaseModel):
    name: str
    skill_gaps: list[str]
    proficiency: dict[str, str]

class UserCredentials(BaseModel):
    username: str
    password: str

class UserAnswer(BaseModel):
    question: str
    user_answer: str

class QuizSubmission(BaseModel):
    user: UserCredentials
    answers: list[UserAnswer]


# Register user in the database
# Replace your login and register endpoints with these fixed versions:

@app.post("/login/")
async def login_user(credentials: UserCredentials, db: AsyncSession = Depends(get_db)):
    """API endpoint for user login"""
    try:
        print(f"Login attempt for username: {credentials.username}")  # Debug log
        
        username = credentials.username
        password = credentials.password
        user = await user_login(username, password, db)
        
        if user:
            print(f"Login successful for user: {user.username}")  # Debug log
            return {
                "success": True,
                "username": user.username,
                "message": "Login successful!"
            }
        else:
            print("Login failed - invalid credentials")  # Debug log
            return {
                "success": False,
                "message": "Invalid credentials"
            }
    except Exception as e:
        print(f"Login error: {str(e)}")  # Debug log
        raise HTTPException(status_code=500, detail=f"Login error: {str(e)}")

@app.post("/register/")
async def register_user(credentials: UserCredentials, db: AsyncSession = Depends(get_db)):
    """API endpoint for user registration"""
    try:
        print(f"Registration attempt for username: {credentials.username}")  # Debug log
        
        username = credentials.username
        password = credentials.password
        user = await user_register(username, password, db)
        
        if user:
            print(f"Registration successful for user: {user.username}")  # Debug log
            return {
                "success": True,
                "username": user.username,
                "message": "Registration successful!"
            }
        else:
            print("Registration failed - username already exists")  # Debug log
            return {
                "success": False,
                "message": "Username already exists"
            }
    except Exception as e:
        print(f"Registration error: {str(e)}")  # Debug log
        raise HTTPException(status_code=500, detail=f"Registration error: {str(e)}")

# Generate MCQs based on user profile
# @app.post("/generate_mcq/")
# async def generate_mcq(user_profile: UserProfile, db: Session = Depends(get_db)):
#     """API endpoint to generate MCQs based on user profile"""
#     mcq_questions_text = generate_mcq_questions(user_profile.model_dump())
#     print(mcq_questions_text)
#     mcqs = parse_mcqs(mcq_questions_text)

#     # Store questions in the database
#     user = await get_user_by_username(user_profile.name)
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     await store_mcq_questions(user.user_id, mcqs)
    
#     return {"message": "MCQs generated and stored successfully!", "questions": mcqs}



# Fixed /generate_mcq/ endpoint in your main.py

@app.post("/generate_mcq/")
async def generate_mcq(user_profile: UserProfile, db: AsyncSession = Depends(get_db)):
    try:
        print(f"Generating MCQs for profile: {user_profile.model_dump()}")
        
        # Generate MCQ questions using the profile
        mcq_questions_text = generate_mcq_questions(user_profile.model_dump())
        mcqs = parse_mcqs(mcq_questions_text)
        
        if not mcqs:
            raise HTTPException(status_code=500, detail="Failed to generate valid MCQs")

        # Get user by name from the profile
        user = await get_user_by_username(user_profile.name, db)
        if not user:
            # If user doesn't exist, create a temporary user for this session
            # Or you might want to handle this differently based on your requirements
            print(f"User {user_profile.name} not found in database")
            # For now, we'll still return the questions without storing them
            return {"message": "MCQs generated successfully!", "questions": mcqs}

        # Store questions in the database
        await store_mcq_questions(user.user_id, mcqs, db)
        
        return {"message": "MCQs generated and stored successfully!", "questions": mcqs}
        
    except Exception as e:
        print(f"Error in generate_mcq: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate MCQs: {str(e)}")




@app.post("/quiz/")
async def take_quiz(submission: QuizSubmission, db: AsyncSession = Depends(get_db)):
    # Step 1: Authenticate user
    user_obj = await user_login(submission.user.username, submission.user.password, db)
    if not user_obj:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    user_id = user_obj.user_id
    print(user_id)

    # Step 2: Fetch quiz questions for this user
    mcqs = await get_quiz_questions_by_user(user_id, db)
    print("++++++++++++MCQS+++++++++++++")
    print(mcqs)
    print("CHECKPOINT 1")

    # Step 3: Normalize and map question to correct answer
    mcqs_by_question = {
        
        (q.question or '').strip().lower(): (q.correct_answer or '').strip().lower()
        for q in mcqs

    
    }
    print("CHECKPOINT 2")

    # Step 4: Normalize user answers and evaluate
    correct = 0
    total = len(submission.answers)
    results = {}

    for idx, item in enumerate(submission.answers):
        # question = item.question.strip().lower()
        # user_answer = item.user_answer.strip().lower()
        # correct_answer = mcqs_by_question.get(question)

        question = (item.question or '').strip().lower()
        user_answer = (item.user_answer or '').strip().lower()
        correct_answer = mcqs_by_question.get(question)

        is_correct = correct_answer == user_answer
        if is_correct:
            correct += 1

        # results[idx] = {
        #     "question": item.question.strip(),
        #     "user_answer": item.user_answer.strip(),
        #     "correct_answer": correct_answer,
        #     "is_correct": is_correct
        # }

        # # Store each answer
        # await store_user_answers(
        #     user_id=user_id,
        #     question=item.question.strip(),
        #     user_answer=item.user_answer.strip(),
        #     correct_answer=correct_answer,
        #     db=db
        # )

        results[idx] = {
            "question": (item.question or '').strip(),
            "user_answer": (item.user_answer or '').strip(),
            "correct_answer": correct_answer,
            "is_correct": is_correct
        }

        # Store each answer safely
        await store_user_answers(
            user_id=user_id,
            question=(item.question or '').strip(),
            user_answer=(item.user_answer or '').strip(),
            correct_answer=correct_answer,
            db=db
        )

    # Step 5: Prepare response
    detailed_results = []
    for res in results.values():
        status = "Correct" if res['is_correct'] else f"Wrong (Correct: {res['correct_answer']})"
        detailed_results.append({
            "question": res['question'],
            "your_answer": res['user_answer'],
            "status": status
        })

    return {
        "score": correct,
        "total": total,
        "detailed_results": detailed_results
    }



@app.post("/recommend_courses/")
async def recommend_courses(user_profile: UserProfile, quiz_results: dict, db: Session = Depends(get_db)):
    # Step 1: Get user from username
    user = await get_user_by_username(user_profile.name)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Step 2: Generate AI-based course recommendations
    recommendations = generate_course_recommendations(user_profile.model_dump(), quiz_results)

    # Step 3: Store in DB
    await store_recommended_courses(user.user_id, recommendations, db)

    # Step 4: Return response
    return {"recommendations": recommendations}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

co = cohere.Client('Xjgfl6dBLAECvdjaLurKTCxD9q6gdyJCjsRWB11S')

@app.post("/upload-resume")
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    if file.content_type not in ["application/pdf"]:
        raise HTTPException(status_code=400, detail="Only PDF files are allowed for now")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    # ✅ Save file
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # ✅ Extract text
    try:
        extracted_text = ""
        with fitz.open(file_path) as pdf:
            for page in pdf:
                extracted_text += page.get_text()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing PDF: {str(e)}")

    # ✅ Scrub PII
    cleaned_text = scrub_pii(extracted_text)

    # ✅ Store metadata + raw text only
    new_resume = ResumeUpload(
        filename=filename,
        file_path=file_path,
        content_type=file.content_type,
        uploaded_at=datetime.utcnow()
    )
    db.add(new_resume)
    await db.commit()

    resume_text = ResumeText(
        resume_id=new_resume.id,
        content=extracted_text  # store raw only
    )
    db.add(resume_text)
    await db.commit()

    # ✅ Call Cohere for profiling
    prompt = f"""
You are an intelligent assistant. Based on the following cleaned resume text, extract:
- The candidate's name (if available)
- Top skill gaps (areas to learn more)
- Proficiency levels for known skills

Respond EXACTLY in this JSON format:
{{
  "name": "Candidate Name",
  "skill_gaps": ["Skill1", "Skill2"],
  "proficiency": {{"SkillA": "Intermediate", "SkillB": "Advanced"}}
}}

Resume:
\"\"\"{cleaned_text}\"\"\"
"""

    response = co.generate(
        model="command-r-plus",
        prompt=prompt,
        max_tokens=300,
        temperature=0.3
    )

    try:
        profile_json = json.loads(response.generations[0].text.strip())
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Cohere output is not valid JSON.")

    return JSONResponse(status_code=200, content={
        # "filename": filename,
        # "message": "Resume uploaded, parsed, PII scrubbed, profiled successfully",
        # "file_path": file_path,
        "profile": profile_json,
        # "raw_preview": extracted_text[:300],
        # "scrubbed_preview": cleaned_text[:300]
    })



@app.on_event("startup")
async def on_startup():
    await setup_database()

# Run the FastAPI app with `uvicorn main:app --reload`
