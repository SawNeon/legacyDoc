# api.py
import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from starlette.staticfiles import StaticFiles

from main import process_single_file

app = FastAPI(title="Legacy Doc API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
os.makedirs("pdfs", exist_ok=True)

app.mount("/pdfs", StaticFiles(directory="pdfs"), name="pdfs")

class DocumentRequest(BaseModel):
    github_url: str
    file_path: str

@app.post("/api/generate")
async def generate_documentation(request: DocumentRequest):
    print(f"📡 Request received via API for the file: {request.file_path}")

    try:
        result = process_single_file(request.github_url, request.file_path)

        return {
            "status": "success",
            "file": result["file"],
            "documentation": result["documentation"],
            "pdf_url": f"/pdfs/{result['pdf_filename']}"
        }
    except Exception as e:
        print(f"Erro na API: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    json_files = os.listdir("data")
    all_data = []

    for file in json_files:
        if file.endswith(".json"):
            with open(f"data/{file}", "r", encoding="utf-8") as f:
                function_arrey = json.load(f)
                all_data.append({
                    "nome_do_arquivo": file.replace(".json", ""),
                    "funcoes": function_arrey
                })

    return {
        "total_modules": len(all_data),
        "modules": all_data
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)