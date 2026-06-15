import json
import os
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.staticfiles import StaticFiles

from api.auth import (
    CurrentUser,
    TokenResponse,
    UserLogin,
    UserRegister,
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
    init_auth_db,
)
from main import process_single_file, safe_print

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.getenv("LEGACYDOC_DATA_DIR", BASE_DIR / "storage")).resolve()
PDF_DIR = DATA_ROOT / "pdfs"
MARKDOWN_DIR = DATA_ROOT / "markdowns"
JSON_DIR = DATA_ROOT / "data"


def get_allowed_origins() -> list[str]:
    raw_origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


app = FastAPI(title="Legacy Doc API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PDF_DIR.mkdir(parents=True, exist_ok=True)
MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
JSON_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/pdfs", StaticFiles(directory=str(PDF_DIR)), name="pdfs")
app.mount("/markdowns", StaticFiles(directory=str(MARKDOWN_DIR)), name="markdowns")
app.mount("/data", StaticFiles(directory=str(JSON_DIR)), name="data")


@app.on_event("startup")
def startup() -> None:
    init_auth_db()


class DocumentRequest(BaseModel):
    github_url: str
    file_path: str
    output_format: str = "pdf"


@app.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(request: UserRegister):
    user = create_user(request.email, request.password)
    return TokenResponse(access_token=create_access_token(user))


@app.post("/auth/login", response_model=TokenResponse)
async def login(request: UserLogin):
    user = authenticate_user(request.email, request.password)
    return TokenResponse(access_token=create_access_token(user))


@app.get("/auth/me", response_model=CurrentUser)
async def me(current_user: CurrentUser = Depends(get_current_user)):
    return current_user


@app.post("/api/generate")
async def generate_documentation(
    request: DocumentRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    safe_print(f"Request received via API for file: {request.file_path}")

    try:
        result = process_single_file(
            request.github_url,
            request.file_path,
            request.output_format,
        )

        return {
            "status": "success",
            "file": result["file"],
            "documentation": result["documentation"],
            "pdf_url": result["pdf_url"],
            "markdown_url": result["markdown_url"],
            "json_url": result["json_url"],
        }
    except FileNotFoundError as fnf_error:
        safe_print(f"File not found: {fnf_error}")
        raise HTTPException(status_code=404, detail=str(fnf_error)) from fnf_error
    except Exception as exc:
        safe_print(f"Error in API: {exc}")
        raise HTTPException(status_code=500, detail="Error processing.") from exc


@app.get("/api/dashboard/stats")
async def get_dashboard_stats(current_user: CurrentUser = Depends(get_current_user)):
    all_data = []

    for file_path in JSON_DIR.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                function_array = json.load(file)
                all_data.append(
                    {
                        "nome_do_arquivo": file_path.stem,
                        "funcoes": function_array,
                    }
                )
        except Exception as exc:
            safe_print(f"Error reading file {file_path.name}: {exc}")

    return {
        "total_modules": len(all_data),
        "modules": all_data,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
