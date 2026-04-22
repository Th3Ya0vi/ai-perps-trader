import json
import re


def parse_json(text: str) -> dict:
    """Parse JSON from an LLM response, stripping markdown fences if present."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    if not text:
        raise ValueError("Empty response")
    return json.loads(text)
