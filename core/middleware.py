import logging
import time
import uuid


logger = logging.getLogger("kitunga")


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID", "")[:64] or str(uuid.uuid4())
        request.request_id = request_id
        started_at = time.monotonic()
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
            },
        )
        return response
