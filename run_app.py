#!/usr/bin/env python3
"""Run the FastAPI app with better error handling."""

import sys
import traceback

print("Starting Perfect Resume application...")
print("=" * 50)

try:
    print("Loading app module...")
    import app
    print("✓ App module loaded successfully")
    
    print("\nStarting server on http://127.0.0.1:5000")
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    
    import uvicorn
    uvicorn.run(app.app, host="127.0.0.1", port=5000, log_level="info")
    
except KeyboardInterrupt:
    print("\n\nServer stopped by user")
except Exception as e:
    print(f"\n✗ Error starting application: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)

