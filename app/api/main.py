import os
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as analysis_router
from app.api.upload import router as upload_router
from app.api.request_limits import RequestBodyLimitsMiddleware
from app.logging_config import configure_application_logging
from app.security import MAX_REQUEST_BODY_SIZE_BYTES
from app.storage.database import initialize_database


# ---------------------------------------------------------
# Application setup
# ---------------------------------------------------------

configure_application_logging()
initialize_database()

app = FastAPI(
    title="Autonomous Data Analyst",
    description="Agentic AI system for autonomous dataset analysis.",
    version="1.0.0",
)
app.state.max_request_body_size_bytes = MAX_REQUEST_BODY_SIZE_BYTES

# Installed before CORS so rejected body-limit responses still receive the
# configured CORS headers. Counts streamed bytes before route/form parsing.
app.add_middleware(
    RequestBodyLimitsMiddleware,
    max_body_bytes=MAX_REQUEST_BODY_SIZE_BYTES,
    receive_timeout_seconds=30,
)


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def get_allowed_origins(app_base_url: str | None = None) -> list[str]:
    """
    Construct the validated list of permitted CORS origins.
    Always includes default local development origins (localhost:3000, 127.0.0.1:3000).
    If APP_BASE_URL (or passed app_base_url) is configured, parses, validates, and normalizes
    it to scheme://netloc (omitting paths, query strings, and trailing slashes).
    Wildcards and invalid schemes are strictly rejected to ensure no wildcard origins
    are permitted.
    """
    origins = set(DEFAULT_ALLOWED_ORIGINS)
    candidate = (
        app_base_url
        if app_base_url is not None
        else os.getenv("APP_BASE_URL", "")
    ).strip()

    if candidate:
        parsed = urlparse(candidate)
        if (
            parsed.scheme in ("http", "https")
            and parsed.netloc
            and parsed.netloc != "*"
            and "*" not in parsed.netloc
        ):
            origins.add(f"{parsed.scheme}://{parsed.netloc}")

    return sorted(origins)


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# Reports and charts are private application data. They must not be mounted
# through StaticFiles; authenticated asset delivery is implemented separately.


# ---------------------------------------------------------
# API routes
# ---------------------------------------------------------

app.include_router(
    analysis_router,
    prefix="/api",
)

app.include_router(
    upload_router,
    prefix="/api",
)


# ---------------------------------------------------------
# Root
# ---------------------------------------------------------

@app.get("/")
def root():
    return {
        "service": "Autonomous Data Analyst",
        "status": "running",
        "api": "/api",
    }
