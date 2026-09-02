import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

from anthropic import Anthropic

import config

client = Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unnamed"


def _extract_text(resp) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()


def _parse_json_loose(text: str) -> dict:
    cleaned = re.sub(r"^```(json)?", "", text.strip(), flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned.strip()).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


UNVERIFIED_TAG = "unverified — model-generated"

# Matches a trailing "[source: ...]" or "[unverified ...]" tag on a tendency line, so the tag can
# round-trip through the plain-text "one per line" textarea in the UI without a schema change there.
_TAG_RE = re.compile(r"\s*\[\s*(?:source:\s*(?P<src>.+?)|unverified[^\]]*)\s*\]\s*$", re.IGNORECASE)


def _format_tendency(text: str, source: Optional[str]) -> str:
    text = (text or "").strip()
    source = (source or "").strip()
    return f"{text} [source: {source}]" if source else f"{text} [{UNVERIFIED_TAG}]"


def _parse_tendency_line(line: str) -> Dict[str, Optional[str]]:
    line = (line or "").strip()
    m = _TAG_RE.search(line)
    if not m:
        # No recognizable tag at all — e.g. a line typed by hand — so it carries no citation.
        return {"text": line, "source": None}
    text = line[: m.start()].strip()
    src = m.group("src")
    return {"text": text, "source": src.strip() if src else None}


def _normalize_tendencies(raw) -> List[Dict[str, Optional[str]]]:
    """Accepts the new [{"text","source"}], plain tagged/untagged strings, or old plain-string
    profiles, and always returns a normalized list of {"text", "source"} dicts."""
    out = []
    for item in raw or []:
        if isinstance(item, dict):
            text = (item.get("text") or "").strip()
            source = item.get("source")
            source = source.strip() if isinstance(source, str) and source.strip() else None
            if text:
                out.append({"text": text, "source": source})
        elif isinstance(item, str):
            parsed = _parse_tendency_line(item)
            if parsed["text"]:
                out.append(parsed)
    return out


def _normalize_cases(raw) -> List[Dict[str, str]]:
    out = []
    for item in raw or []:
        if isinstance(item, dict):
            out.append({
                "case_name": item.get("case_name", ""),
                "summary": item.get("summary", ""),
                "source": item.get("source") or None,
            })
    return out


@dataclass
class Profile:
    name: str
    role: str = "counsel"  # "judge" or "counsel"
    bio: str = ""
    tendencies: List[Dict[str, Optional[str]]] = field(default_factory=list)
    notable_cases: List[Dict[str, str]] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    confidence_note: str = ""
    manual_notes: str = ""
    auto_researched: bool = False
    found: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        # Render tendencies as tagged display strings so the "one per line" textarea in the UI can
        # show, edit, and round-trip the unverified/sourced status without any frontend schema change.
        d["tendencies"] = [_format_tendency(t.get("text"), t.get("source")) for t in self.tendencies]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Profile":
        return Profile(
            name=d.get("name", ""),
            role=d.get("role", "counsel"),
            bio=d.get("bio", ""),
            tendencies=_normalize_tendencies(d.get("tendencies")),
            notable_cases=_normalize_cases(d.get("notable_cases")),
            sources=list(d.get("sources") or []),
            confidence_note=d.get("confidence_note", ""),
            manual_notes=d.get("manual_notes", ""),
            auto_researched=bool(d.get("auto_researched", False)),
            found=bool(d.get("found", True)),
        )


def _cache_path(name: str) -> str:
    return os.path.join(config.PROFILES_DIR, f"{_slug(name)}.json")


def load_cached_profile(name: str) -> Optional[Profile]:
    path = _cache_path(name)
    if os.path.exists(path):
        with open(path) as f:
            return Profile.from_dict(json.load(f))
    return None


def save_profile(profile: Profile) -> Profile:
    with open(_cache_path(profile.name), "w") as f:
        json.dump(profile.to_dict(), f, indent=2)
    return profile


RESEARCH_SYSTEM = """You are a legal research assistant building a PUBLIC-RECORD-ONLY professional \
profile of a named legal professional (a judge or an attorney), for an internal legal-strategy \
simulation tool. You MUST use the web_search tool to find real, retrievable public sources — \
published opinions, court dockets, news coverage, law firm or court bios, bar association pages, \
published articles or interviews, CLE materials, and similar — before writing anything. Do not \
answer from general knowledge alone.

For every tendency and every notable case you report, you must attach the specific URL you found \
it in. If a pattern seems plausible or is a reasonable inference from general legal practice but \
you did NOT find it stated in a retrieved source, you must still include it if useful — but leave \
its "source" field null so it is visibly marked as an inference rather than a documented fact. \
Never fabricate a source URL to make an inference look documented; an absent source is fine and \
expected for reasonable inferences, a fake source is not. Never fabricate cases, quotes, or \
rulings. If you cannot find meaningful public information about this specific person, say so \
honestly instead of inventing detail."""


def research_profile(name: str, role: str, hint: str = "") -> Profile:
    """Research a named legal professional's public record using web search, cache, and return it.

    Every reported tendency and notable case must carry the source URL it was actually found in;
    anything the model could not ground in a retrieved source is still returned, but with a null
    source, so the caller (and the persona system prompt) can visibly tag it as unverified rather
    than presenting a plausible guess as documented history.
    """
    user_prompt = f"""Research the public professional record of: {name}
Role: {"presiding judge" if role == "judge" else "attorney / counsel"}
Additional disambiguating context (may be blank): {hint or "(none provided)"}

Use the web_search tool — actually search, do not rely on memory — to find real, verifiable public \
information. Then respond with ONLY a JSON object (no markdown fences, no commentary before or \
after) matching exactly this schema:

{{
  "found": true or false,
  "bio": "2-4 sentence professional biography",
  "tendencies": [
    {{"text": "short bullet describing a documented pattern, tendency, or notable stance",
      "source": "https://... the specific URL this came from, or null if this is a reasonable
      inference you did not find directly documented"}}
  ],
  "notable_cases": [
    {{"case_name": "...", "summary": "one sentence on the case and the outcome or opinion",
      "source": "https://... the specific URL, or null if not directly documented"}}
  ],
  "sources": ["https://...", "https://..."],
  "confidence_note": "1-2 honest sentences on how complete/reliable this profile is, and roughly \
how many of the tendencies above are sourced versus inferred"
}}

If you cannot confidently identify a real, public professional matching this name and role, set \
"found" to false and explain briefly in "confidence_note" rather than guessing or inventing detail."""

    resp = client.messages.create(
        model=config.RESEARCH_MODEL,
        max_tokens=2048,
        system=RESEARCH_SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = _extract_text(resp)
    try:
        data = _parse_json_loose(text)
    except Exception:
        data = {
            "found": False,
            "bio": "",
            "tendencies": [],
            "notable_cases": [],
            "sources": [],
            "confidence_note": f"Could not parse research output. Raw model output (truncated): {text[:500]}",
        }

    profile = Profile(
        name=name,
        role=role,
        bio=data.get("bio", "") or "",
        tendencies=_normalize_tendencies(data.get("tendencies")),
        notable_cases=_normalize_cases(data.get("notable_cases")),
        sources=list(data.get("sources") or []),
        confidence_note=data.get("confidence_note", "") or "",
        auto_researched=True,
        found=bool(data.get("found", True)),
    )
    return save_profile(profile)
