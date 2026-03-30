from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

def setup_cors(app: FastAPI):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # In production, this should be restricted to the exact dashboard origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
