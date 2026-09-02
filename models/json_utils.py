import json
from typing import Optional


def extract_text(resp) -> str:
    """Join every text block in a Messages API response. Joined with newlines (not
    concatenated raw) because multi-step tool use (e.g. web_search) can return several separate
    text blocks in one response, and gluing them together with no separator produces garbled,
    unparseable output."""
    return "\n".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()


def _find_json_object(text: str) -> Optional[str]:
    """Scan for the first balanced top-level {...} object in `text`, correctly skipping over
    braces inside string literals. This is robust against the things that break a naive greedy
    regex like r"\\{.*\\}": leading prose before the JSON, trailing commentary or a closing
    markdown fence after it, and multiple JSON-looking blobs in the same response — all of which
    become more likely once a research step involves several rounds of tool use."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None  # never balanced — output was likely truncated


def parse_json_loose(text: str) -> dict:
    """Extract and parse the first well-formed JSON object found anywhere in `text`, tolerating
    leading/trailing prose and markdown fences around it."""
    candidate = _find_json_object(text)
    if candidate is None:
        raise ValueError("No JSON object found in model output.")
    return json.loads(candidate)
