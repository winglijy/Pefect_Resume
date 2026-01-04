#!/usr/bin/env python3
"""Quick test to verify AI Builder API works with different models."""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url='https://space.ai-builders.com/backend/v1',
    api_key=os.getenv('AI_BUILDER_TOKEN')
)

# Test models
models = ['deepseek', 'gemini-2.5-pro', 'grok-4-fast']

test_message = [
    {"role": "system", "content": "You are a helpful assistant. Return JSON only."},
    {"role": "user", "content": 'Return this JSON: {"test": "success", "model": "working"}'}
]

print("Testing AI Builder API models...\n")
print(f"API Token set: {bool(os.getenv('AI_BUILDER_TOKEN'))}\n")

for model in models:
    print(f"Testing {model}...")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=test_message,
            max_tokens=100,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        print(f"  ✓ SUCCESS: {content[:100]}")
    except Exception as e:
        print(f"  ✗ FAILED: {str(e)[:100]}")
    print()

print("Done!")

