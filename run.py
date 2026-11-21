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

import uvicorn
from dotenv import load_dotenv

# Load .env from the backend directory (or parent)
_here = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_here, ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
    print(f"✅ Loaded environment from {_env_path}")
else:
    print(f"ℹ️  No .env file found at {_env_path} — using system environment variables")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meeting-to-Execution Agent Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (dev only)")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    args = parser.parse_args()

    print(f"\n🚀 Starting Meeting-to-Execution Agent")
    print(f"   Host:      {args.host}:{args.port}")
    print(f"   Demo Mode: {os.getenv('DEMO_MODE', 'false')}")
    print(f"   Database:  {os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./meeting_agent.db')}")
    print(f"   Docs:      http://localhost:{args.port}/docs\n")

    uvicorn.run(
        "backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=1 if args.reload else args.workers,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
