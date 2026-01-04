#!/usr/bin/env python3
"""Test gpt-5 specifically."""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url='https://space.ai-builders.com/backend/v1',
    api_key=os.getenv('AI_BUILDER_TOKEN')
)

test_message = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": 'Say hello and return a simple JSON like {"greeting": "hello"}'}
]

print("Testing gpt-5...")

# Test 1: Without json_mode
print("\n1. Without json_mode:")
try:
    response = client.chat.completions.create(
        model='gpt-5',
        messages=test_message,
        max_tokens=100
    )
    content = response.choices[0].message.content
    print(f"  ✓ SUCCESS: {content[:200] if content else 'EMPTY'}")
except Exception as e:
    print(f"  ✗ FAILED: {e}")

# Test 2: With json_mode
print("\n2. With json_mode:")
try:
    response = client.chat.completions.create(
        model='gpt-5',
        messages=test_message,
        max_tokens=100,
        response_format={"type": "json_object"}
    )
    content = response.choices[0].message.content
    print(f"  ✓ SUCCESS: {content[:200] if content else 'EMPTY'}")
except Exception as e:
    print(f"  ✗ FAILED: {e}")

print("\nDone!")

