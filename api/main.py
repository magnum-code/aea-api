# ════════════════════════════════════════════════════════════════════════
#  main.py — AEA Command Center FastAPI App
# ════════════════════════════════════════════════════════════════════════

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import mis, attendance, other

app = FastAPI(
    title="AEA Command Center API",
    description="Backend API for AEA Command Center — replaces Google Apps Script",
    version="1.0.0",
)

# CORS — allow your Apps Script domain and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten this once you know your frontend domain
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Routers
app.include_router(mis.router,        prefix="/api")
app.include_router(attendance.router, prefix="/api")
app.include_router(other.router,      prefix="/api")


@app.get("/")
def root():
    return {"status": "ok", "service": "AEA Command Center API"}


@app.get("/health")
def health():
    return {"status": "ok"}
