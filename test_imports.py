#!/usr/bin/env python3
"""Test script to check for import errors."""

print("Testing imports...")

try:
    print("1. Testing basic imports...")
    import os
    import json
    import uuid
    from pathlib import Path
    print("   ✓ Basic imports OK")
except Exception as e:
    print(f"   ✗ Basic imports failed: {e}")
    exit(1)

try:
    print("2. Testing dotenv...")
    from dotenv import load_dotenv
    load_dotenv()
    print("   ✓ dotenv OK")
except Exception as e:
    print(f"   ✗ dotenv failed: {e}")
    exit(1)

try:
    print("3. Testing OpenAI client...")
    from openai import OpenAI
    token = os.getenv('AI_BUILDER_TOKEN')
    if not token:
        print("   ⚠ Warning: AI_BUILDER_TOKEN not found in environment")
    else:
        print(f"   ✓ OpenAI client OK (token found: {token[:10]}...)")
except Exception as e:
    print(f"   ✗ OpenAI client failed: {e}")
    exit(1)

try:
    print("4. Testing FastAPI...")
    from fastapi import FastAPI
    print("   ✓ FastAPI OK")
except Exception as e:
    print(f"   ✗ FastAPI failed: {e}")
    exit(1)

try:
    print("5. Testing SQLAlchemy...")
    from sqlalchemy import create_engine
    print("   ✓ SQLAlchemy OK")
except Exception as e:
    print(f"   ✗ SQLAlchemy failed: {e}")
    exit(1)

try:
    print("6. Testing project modules...")
    from src.config import ai_client
    from src.models import schemas
    from src.parsers import resume_parser, jd_parser
    print("   ✓ Project modules OK")
except Exception as e:
    print(f"   ✗ Project modules failed: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n✅ All imports successful!")
print("\nYou can now run: python app.py")

