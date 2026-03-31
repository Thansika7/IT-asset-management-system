import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI


def setup_cors(app: FastAPI):
    raw = os.getenv("CORS_ORIGINS", "*").strip()
    if raw == "*":
        allow_origins = ["*"]
        allow_credentials = False
    else:
        allow_origins = [o.strip() for o in raw.split(",") if o.strip()]
        if not allow_origins:
            allow_origins = ["*"]
            allow_credentials = False
        else:
            allow_credentials = True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
