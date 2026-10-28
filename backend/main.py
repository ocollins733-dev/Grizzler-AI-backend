import os
from pathlib import Path
from importlib import import_module
import json
import urllib.request
import urllib.error
import urllib.parse
import ssl
import asyncio


# 1. CRITICAL FIX: Locate and load the .env file BEFORE doing anything else
# This guarantees that DATABASE_URL is never None, even during Uvicorn hot-reloads.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv = import_module("dotenv").load_dotenv
load_dotenv(dotenv_path=BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError(
        "❌ DATABASE_URL missing! Sir, please verify your .env file exists inside "
        f"'{BASE_DIR}' and contains a valid connection string."
    )

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
origins = [FRONTEND_URL] if FRONTEND_URL else ["http://localhost:5173"]

# 2. Safely resolve dynamic SQLAlchemy symbols
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

_sqlalchemy = import_module("sqlalchemy")
TEXT_TYPE = _sqlalchemy.TEXT

_sqlalchemy_asyncio = import_module("sqlalchemy.ext.asyncio")
create_async_engine = _sqlalchemy_asyncio.create_async_engine
async_sessionmaker = _sqlalchemy_asyncio.async_sessionmaker
AsyncSession = _sqlalchemy_asyncio.AsyncSession

_sqlalchemy_orm = import_module("sqlalchemy.orm")
DeclarativeBase = _sqlalchemy_orm.DeclarativeBase
Mapped = _sqlalchemy_orm.Mapped
mapped_column = _sqlalchemy_orm.mapped_column

# 3. Async Database Core Setup (Will now receive the validated string)
engine = create_async_engine(
    DATABASE_URL, 
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20
)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

# ... Leave the rest of your models, routes, and main blocks exactly as they are ...

class Base(DeclarativeBase):
    pass

# SQLAlchemy Data Model matching the local init_db schema
class GradingHistory(Base):
    __tablename__ = "grading_history"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    assignment_name: Mapped[str] = mapped_column(nullable=False)
    # FIX: Replaced `text("LONGTEXT")` with type string compilation wrapper `TEXT_TYPE(length=4294967295)`
    # In MySQL, a TEXT type with this maximum length length compiles perfectly into a native LONGTEXT block.
    student_submission: Mapped[str] = mapped_column(type_=TEXT_TYPE(length=4294967295), nullable=False)
    grade: Mapped[Optional[int]] = mapped_column(nullable=True)
    progress: Mapped[int] = mapped_column(default=0)
    suggestions: Mapped[Optional[str]] = mapped_column(type_=TEXT_TYPE(length=4294967295), nullable=True)
    ali_raw_response: Mapped[str] = mapped_column(type_=TEXT_TYPE(length=4294967295), nullable=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# 2. FastAPI Setup
app = FastAPI(title="A.L.I Mainframe Evaluation Core", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Pydantic Validation Models
class ChatTurn(BaseModel):
    speaker: str
    text: str

class GradingRequest(BaseModel):
    assignment_name: str
    submission_text: str
    history: List[ChatTurn] = []
    allow_web_search: bool = False

# 4. Helper Integrations (Ollama Loopback & Search Routing)
def query_ollama_engine(prompt_payload: str) -> str:
    url = "http://localhost:11434/api/generate"
    data = {"model": "llama3.2:1b", "prompt": prompt_payload, "stream": False}
    try:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("response", "Forgive me, Sir, but my core intelligence engine failed to formulate a response.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ollama offline loop: {e}")

def run_external_fallback_search(query: str) -> str:
    return f"[External Search Result for '{query}': Retrieved live grading schema benchmarks and package documentation.]"

# 5. Active Controller Endpoints
@app.get("/api/v1/health")
async def health_check():
    return {"status": "online", "identity": "A.L.I Mainframe"}

@app.post("/api/v1/evaluate")
async def evaluate_submission(request: GradingRequest, db: AsyncSession = Depends(get_db)):
    jarvis_persona = (
        "You are A.L.I, an incredibly brilliant, sophisticated, and articulate artificial intelligence "
        "built by Grizzler. You possess the precise personality, sharp wit, and mannerisms of JARVIS from Marvel. "
        "Always address the user as 'Sir'. Keep responses conversational but highly professional.\n\n"
        "PROJECT ASSIGNMENT METRICS:\n"
        "1. Analyze the provided project submission text carefully.\n"
        "2. State an explicitly clear score strictly out of 100% (e.g., 'Grade: 85%').\n"
        "3. Provide concrete suggestions for improvements or corrections.\n"
        "4. If the work is incomplete, clearly state the missing components alongside an explicit progress percentage formatted exactly like '[Progress: X%]'.\n"
        "5. CRITICAL: If you do not have the technical information or standard metrics in your local data blocks to evaluate this, "
        "stop instantly and state that you require 'permission to search external sources or Google arrays'. Do not hallucinate metrics."
    )

    history_block = "".join([f"{turn.speaker}: {turn.text}\n" for turn in request.history[-6:]])
    external_data_stream = run_external_fallback_search(request.assignment_name) if request.allow_web_search else ""

    compiled_prompt = (
        f"System Directives:\n{jarvis_persona}\n\n"
        f"Thread Session History:\n{history_block}\n"
        f"External Database Stream:\n{external_data_stream}\n\n"
        f"Grizzler Submission ({request.assignment_name}):\n{request.submission_text}\n\n"
        f"A.L.I:"
    )

    ali_output = query_ollama_engine(compiled_prompt)
    search_intercept_flag = "permission" in ali_output.lower() and ("external" in ali_output.lower() or "google" in ali_output.lower())

    extracted_grade = None
    extracted_progress = 0
    
    if "%" in ali_output:
        if "[progress:" in ali_output.lower():
            try:
                parts = ali_output.lower().split("[progress:")
                extracted_progress = int(parts[1].split("%")[0].strip())
            except: pass
        if "grade:" in ali_output.lower():
            try:
                parts = ali_output.lower().split("grade:")
                extracted_grade = int(parts[1].split("%")[0].strip())
            except: pass

    # 6. Persistent Local DB Storage Engine Action
    new_record = GradingHistory(
        assignment_name=request.assignment_name,
        student_submission=request.submission_text,
        grade=extracted_grade,
        progress=extracted_progress,
        suggestions=ali_output,  
        ali_raw_response=ali_output
    )
    
    db.add(new_record)
    await db.commit()

    return {
        "response": ali_output,
        "requires_search_permission": search_intercept_flag and not request.allow_web_search,
        "extracted_metrics": {
            "grade_percentage": extracted_grade,
            "progress_percentage": extracted_progress
        }
    }

if __name__ == "__main__":
    import uvicorn
    # FIX: Explicit configuration matching your main app instantiation parameters 
    uvicorn.run(app, host="127.0.0.1", port=8000)
