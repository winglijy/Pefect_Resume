import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Initialize OpenAI client with AI Builder API
ai_client = OpenAI(
    base_url='https://space.ai-builders.com/backend/v1',
    api_key=os.getenv('AI_BUILDER_TOKEN')
)

# For embeddings
def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get embeddings for a list of texts using AI Builder API."""
    response = ai_client.embeddings.create(
        model='text-embedding-3-small',
        input=texts
    )
    return [item.embedding for item in response.data]

# For chat completions (suggestions)
# Supported models: deepseek, supermind-agent-v1, gemini-2.5-pro, gemini-3-flash-preview, gpt-5, grok-4-fast
def generate_chat_completion(messages: list[dict], model: str = 'gpt-5', json_mode: bool = False) -> str:
    """Generate chat completion using AI Builder API."""
    try:
        # Check if API key is set
        api_key = os.getenv('AI_BUILDER_TOKEN')
        if not api_key:
            raise ValueError("AI_BUILDER_TOKEN not set in environment. Please check your .env file.")
        
        params = {
            'model': model,
            'messages': messages,
            'max_tokens': 8000  # Allow more tokens for detailed suggestions
        }
        
        # gpt-5 only supports temperature=1.0 (server auto-adjusts, but we set it explicitly)
        # Other models can use lower temperature for consistency
        if model == 'gpt-5':
            params['temperature'] = 1.0
        else:
            params['temperature'] = 0.3
        
        if json_mode:
            params['response_format'] = {'type': 'json_object'}
        
        print(f"  Calling API with model={model}, json_mode={json_mode}")
        response = ai_client.chat.completions.create(**params)
        
        if not response or not response.choices:
            raise ValueError("Empty response from API - no choices returned")
        
        content = response.choices[0].message.content
        
        if not content:
            raise ValueError("Empty content in API response")
        
        # Check if response looks like an error message
        if content.startswith(('Error:', 'Internal', 'Failed', 'Exception')):
            raise ValueError(f"API returned error: {content[:200]}")
        
        return content
    except Exception as e:
        error_msg = str(e)
        print(f"Error in generate_chat_completion: {error_msg}")
        
        # Provide helpful error messages
        if "AI_BUILDER_TOKEN" in error_msg:
            print("  → Check your .env file has AI_BUILDER_TOKEN set")
        elif "401" in error_msg or "Unauthorized" in error_msg:
            print("  → API key may be invalid or expired")
        elif "429" in error_msg or "rate limit" in error_msg.lower():
            print("  → Rate limit exceeded, please wait and try again")
        
        import traceback
        traceback.print_exc()
        raise ValueError(f"API call failed: {error_msg}")

