from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def health_request(server: Any, request_id: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://{server.host}:{server.port}/v1/health",
        data=json.dumps(
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": request_id,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return {"status": response.status, "body": json.loads(response.read())}
    except urllib.error.HTTPError as error:
        return {"status": error.code, "body": json.loads(error.read())}
