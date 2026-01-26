#!/usr/bin/env python3
"""
Run the IDML Layout Engine web application.

Usage:
    python run.py [--port PORT] [--host HOST] [--debug]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp.app import app


def main():
    parser = argparse.ArgumentParser(description="Run the IDML Layout Engine web app")
    parser.add_argument("--port", type=int, default=5000, help="Port to run on (default: 5000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    
    args = parser.parse_args()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                  IDML Layout Engine                          ║
║                     Web Application                          ║
╠══════════════════════════════════════════════════════════════╣
║  Running on: http://{args.host}:{args.port}                        ║
║  Debug mode: {'ON' if args.debug else 'OFF'}                                            ║
║                                                              ║
║  Press Ctrl+C to stop                                        ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()
