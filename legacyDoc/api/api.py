from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from main import app as langgraph_app, load_cpp_from_github
from tools.pdf_generator import export_doc_to_pdf

app = FastAPI(title="Legacy API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"], )

class DocstringSchema(BaseModel):
    github_url: str
    file_path: str

@app.post("/api/generate")
async def generate_documentation(request: DocumentRequest):
    print(f"React for documentation: {request.file_path}")

    simulated_json = {
        "summary": f"Successful create pdf {request.file_path}",
        "functions": [{"name": "main", "description": "Função principal"}]
    }

    return {
        "status": "success",
        "file": request.file_path,
        "documentation": simulated_json,
        "pdf_url": f"/pdfs/Doc_{request.file_path.split('/')[-1]}.pdf"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)