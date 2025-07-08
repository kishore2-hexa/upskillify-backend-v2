from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from fastapi import Depends
from sqlalchemy import select
from models import Base, User, QuizQuestion, UserAnswer, RecommendedCourse

# Setup for SQLAlchemy (Async with aiomysql)
DATABASE_URL = "mysql+aiomysql://root:pass%40word1@localhost/upskillify"
engine = create_async_engine(DATABASE_URL, echo=True, future=True)

# Async session setup
SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# Dependency to get the database session
async def get_db():
    async with SessionLocal() as session:
        yield session
        await session.close()

# Function to set up the database (async)
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully!")

# Function to store MCQ questions in the database (Async)
async def store_mcq_questions(user_id: int, mcqs: list, db: AsyncSession):
    """Store MCQ questions in database (normalized)"""
    try:
        for mcq in mcqs:
            question_obj = QuizQuestion(
                user_id=user_id,
                question=mcq['question'].strip(),
                options=str([opt.strip() for opt in mcq['options']]),
                correct_answer=mcq['answer'].strip()
            )
            db.add(question_obj)

        await db.commit()
        print(f"Stored {len(mcqs)} questions for user {user_id}")
        return True
    except Exception as e:
        print(f"Error storing MCQ questions: {e}")
        await db.rollback()
        return False

# Function to get quiz questions for a specific user using external DB session
async def get_quiz_questions_by_user(user_id: int, db: AsyncSession):
    """Fetch quiz questions assigned to a specific user"""
    try:
        print("===> Entered get_quiz_questions_by_user()")
        print(f"===> user_id: {user_id}")

        # Build query
        query = select(QuizQuestion).where(QuizQuestion.user_id == user_id)
        print(f"===> Built query: {query}")

        # Execute query
        result = await db.execute(query)
        print(result)
        print("===> Query executed successfully")

        # Fetch results
        questions = result.scalars().all()
        print(f"===> Retrieved questions: {questions}")

        return questions

    except Exception as e:
        print(f"!!! Error in get_quiz_questions_by_user for user_id {user_id}: {e}")
        return []


# Function to store user's answers (normalized comparison included)
async def store_user_answers(user_id: int, question: str, user_answer: str, correct_answer: str, db: AsyncSession):
    """Store user answers with scoring"""
    try:
        is_correct = user_answer.strip().lower() == correct_answer.strip().lower()
        score = 10 if is_correct else 0

        answer_obj = UserAnswer(
            user_id=user_id,
            question=question.strip(),
            user_answer=user_answer.strip(),
            correct_answer=correct_answer.strip(),
            is_correct=int(is_correct),
            score=score
        )
        db.add(answer_obj)
        await db.commit()
        return True
    except Exception as e:
        print(f"Error storing user answer: {e}")
        await db.rollback()
        return False

# Function to store recommended courses
async def store_recommended_courses(user_id: int, courses: list[dict], db: AsyncSession):
    for course in courses:
        new_course = RecommendedCourse(
            user_id=user_id,
            course_name=course["course_name"],
            platform=course["platform"],
            url=course["url"],
            reason=course["reason"]
        )
        db.add(new_course)
    await db.commit()

# Get user by username
async def get_user_by_username(username: str, db: AsyncSession):
    try:
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()
    except Exception as e:
        print(f"Error getting user by username: {e}")
        return None
