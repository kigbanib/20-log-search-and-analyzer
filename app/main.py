from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.upload import router as upload_router

app = FastAPI(title="Log Search & Analyzer")

# Allow the browser to call us from any origin during dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}