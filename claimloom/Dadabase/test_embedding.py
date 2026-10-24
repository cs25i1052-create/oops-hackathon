
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is missing from .env")

client = genai.Client(api_key=api_key)

response = client.models.embed_content(
    model="gemini-embedding-001",
    contents="Never promise guaranteed investment returns.",
    config=types.EmbedContentConfig(
        output_dimensionality=768,
        task_type="RETRIEVAL_DOCUMENT"
    )
)

embedding = response.embeddings[0].values

print("Embedding generated successfully!")
print("Number of dimensions:", len(embedding))
print("First five values:", embedding[:5])

assert len(embedding) == 768

print("Gemini embedding test passed!")
