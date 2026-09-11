"""
Small shared helper for getting an authenticated google-genai client.

Looks for the key in this order:
  1. GEMINI_API_KEY environment variable (local / any non-Colab environment)
  2. Colab secret named GEMINI_API_KEY (google.colab.userdata)

Set the key once, e.g.:
    export GEMINI_API_KEY="your-key-here"       # local / CI
or add a Colab secret called GEMINI_API_KEY.
"""

import os

from google import genai


def get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key

    try:
        from google.colab import userdata  # type: ignore
        key = userdata.get("GEMINI_API_KEY")
        if key:
            return key
    except ImportError:
        pass

    raise RuntimeError(
        "No Gemini API key found. Set the GEMINI_API_KEY environment variable "
        "(or add a Colab secret named GEMINI_API_KEY)."
    )


def get_client() -> genai.Client:
    return genai.Client(api_key=get_api_key())
