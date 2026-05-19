"""Run Symposa API with uvicorn."""

from __future__ import annotations

import uvicorn

from symposa.api.app import create_app

app = create_app()


def main() -> None:
    uvicorn.run(
        "symposa.api.main:app",
        host="0.0.0.0",
        port=int(__import__("os").getenv("SYMPOSA_API_PORT", "8090")),
        reload=False,
    )


if __name__ == "__main__":
    main()
