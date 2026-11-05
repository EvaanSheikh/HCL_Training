"""Streaming ASGI request-body and receive-time limits for API routes."""
import asyncio

from starlette.responses import JSONResponse


class RequestBodyTooLarge(BaseException):
    pass


class RequestBodyReadTimedOut(BaseException):
    pass


class RequestBodyLimitsMiddleware:
    """Count incoming bytes before FastAPI/Starlette parses or spools a body."""

    def __init__(self, app, *, max_body_bytes: int, receive_timeout_seconds: float = 30):
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.receive_timeout_seconds = receive_timeout_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        app = scope.get("app")
        limit = getattr(getattr(app, "state", None), "max_request_body_size_bytes", self.max_body_bytes)
        content_lengths = [value for name, value in scope.get("headers", []) if name.lower() == b"content-length"]
        if len(content_lengths) > 1:
            await JSONResponse({"detail": "Malformed request."}, status_code=400)(scope, receive, send)
            return
        if content_lengths:
            raw_length = content_lengths[0]
            if not raw_length.isdigit():
                await JSONResponse({"detail": "Malformed request."}, status_code=400)(scope, receive, send)
                return
            if int(raw_length) > limit:
                await JSONResponse({"detail": "Request body exceeds the configured limit."}, status_code=413)(scope, receive, send)
                return

        received = 0
        response_started = False

        async def bounded_receive():
            nonlocal received
            try:
                message = await asyncio.wait_for(receive(), timeout=self.receive_timeout_seconds)
            except TimeoutError as exc:
                raise RequestBodyReadTimedOut() from exc
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestBodyTooLarge()
            return message

        async def track_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, track_send)
        except RequestBodyTooLarge:
            if not response_started:
                await JSONResponse({"detail": "Request body exceeds the configured limit."}, status_code=413)(scope, receive, send)
        except RequestBodyReadTimedOut:
            if not response_started:
                await JSONResponse({"detail": "Request body timed out."}, status_code=408)(scope, receive, send)
