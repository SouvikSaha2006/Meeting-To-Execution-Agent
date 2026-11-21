"""
run.py — Convenience launcher script.

Usage:
    python run.py
    python run.py --port 8080
    python run.py --reload   (development hot-reload)
"""
import argparse
import os
import sys

# Ensure repository root is on sys.path
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from dotenv import load_dotenv

# Try multiple candidate locations for .env
_env_loaded = False
for _candidate in [
    os.path.join(_here, ".env"),
    os.path.join(_here, "backend", ".env"),
]:
    if os.path.exists(_candidate):
        load_dotenv(_candidate, override=True)
        print(f"✅ Loaded environment from {_candidate}")
        _env_loaded = True
        break

if not _env_loaded:
    print("ℹ️  No .env file found — using system environment variables")

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meeting-to-Execution Agent Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (dev only)")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    args = parser.parse_args()

    demo_mode = os.getenv("DEMO_MODE", "false")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    masked_key = (gemini_key[:8] + "..." + gemini_key[-4:]) if len(gemini_key) > 12 else ("(not set)" if not gemini_key else "(set)")

    print(f"\n🚀 Starting Meeting-to-Execution Agent")
    print(f"   Host:         http://localhost:{args.port}")
    print(f"   API Docs:     http://localhost:{args.port}/docs")
    print(f"   Demo Mode:    {demo_mode}")
    print(f"   Gemini Model: {os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')}")
    print(f"   Gemini Key:   {masked_key}")
    print(f"   Database:     {os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./meeting_agent.db')}\n")

    uvicorn.run(
        "backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=1 if args.reload else args.workers,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
