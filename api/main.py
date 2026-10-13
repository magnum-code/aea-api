# ════════════════════════════════════════════════════════════════════════
#  main.py — AEA Command Center FastAPI App
# ════════════════════════════════════════════════════════════════════════

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.routers import mis, attendance, other, saqed

app = FastAPI(
    title="AEA Command Center API",
    description="Backend API for AEA Command Center — replaces Google Apps Script",
    version="1.0.0",
)

# CORS — set ALLOWED_ORIGINS on Render to your Vercel address, e.g.
#   https://aea-command-center.vercel.app,http://localhost:3000
_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
# SAQED replies are large (hundreds of KB); compress them
app.add_middleware(GZipMiddleware, minimum_size=2000)

# Routers
app.include_router(mis.router,        prefix="/api")
app.include_router(attendance.router, prefix="/api")
app.include_router(other.router,      prefix="/api")
app.include_router(saqed.router,      prefix="/api")


@app.get("/")
def root():
    return {"status": "ok", "service": "AEA Command Center API"}


@app.get("/health")
def health():
    return {"status": "ok"}
