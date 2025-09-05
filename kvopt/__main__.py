#!/usr/bin/env python3
"""
KV-OptKit Command Line Interface
"""
import sys
import uvicorn
from .server.main import app

def main():
    """Run the KV-OptKit server."""
    print("Starting KV-OptKit server...")
    uvicorn.run(
        "kvopt.server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="debug"
    )

if __name__ == "__main__":
    main()
