import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response

app = FastAPI()

UPSTREAM = os.environ.get(
    "UPSTREAM_URL",
    "http://18.61.71.233:5173",
).rstrip("/")

EXCLUDED_REQUEST_HEADERS = {
    "host",
    "content-length",
    "connection",
    "transfer-encoding",
}

EXCLUDED_RESPONSE_HEADERS = {
    "content-length",
    "connection",
    "transfer-encoding",
    "content-encoding",
}


@app.api_route(
    "/{path:path}",
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
        "HEAD",
    ],
)
async def proxy(request: Request, path: str):
    url = f"{UPSTREAM}/{path}"

    if request.url.query:
        url += f"?{request.url.query}"

    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in EXCLUDED_REQUEST_HEADERS
    }

    # Tell upstream about the original client request.
    headers["x-forwarded-for"] = request.client.host if request.client else ""
    headers["x-forwarded-proto"] = request.url.scheme
    headers["x-forwarded-host"] = request.headers.get("host", "")

    body = await request.body()

    print(f"{request.method} {request.url.path}")
    print(f"  -> {url}")

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=30.0,
        ) as client:

            upstream_response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )

    except httpx.HTTPError as error:
        print(f"UPSTREAM ERROR: {error!r}")

        return Response(
            content=f"Bad Gateway: {error}",
            status_code=502,
            media_type="text/plain",
        )

    print(
        f"  <- {upstream_response.status_code} "
        f"{len(upstream_response.content)} bytes"
    )

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in EXCLUDED_RESPONSE_HEADERS
    }

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )
