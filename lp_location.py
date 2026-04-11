from __future__ import annotations

import uvicorn


def main() -> None:
    """Run ANPR web dashboard; example: python3 lp_location.py."""

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
