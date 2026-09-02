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


@dataclass
class Profile:
    name: str
    role: str = "counsel"  # "judge" or "counsel"
    bio: str = ""
    tendencies: List[str] = field(default_factory=list)
    notable_cases: List[Dict[str, str]] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    confidence_note: str = ""
    manual_notes: str = ""
    auto_researched: bool = False
    found: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Profile":
        return Profile(
            name=d.get("name", ""),
            role=d.get("role", "counsel"),
            bio=d.get("bio", ""),
            tendencies=list(d.get("tendencies") or []),
            notable_cases=list(d.get("notable_cases") or []),
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
simulation tool. Only use information you can find and reasonably attribute to public sources: \
published opinions, court dockets, news coverage, law firm or court bios, bar association pages, \
published articles or interviews, CLE materials, and similar. Never fabricate cases, quotes, or \
rulings, and never present an inference as a confirmed fact. If you cannot find meaningful public \
information about this specific person, say so honestly instead of inventing detail."""


def research_profile(name: str, role: str, hint: str = "") -> Profile:
    """Research a named legal professional's public record using web search, cache, and return it."""
    user_prompt = f"""Research the public professional record of: {name}
Role: {"presiding judge" if role == "judge" else "attorney / counsel"}
Additional disambiguating context (may be blank): {hint or "(none provided)"}

Use web search to find real, verifiable public information. Then respond with ONLY a JSON object \
(no markdown fences, no commentary before or after) matching exactly this schema:

{{
  "found": true or false,
  "bio": "2-4 sentence professional biography",
  "tendencies": ["short bullet describing a documented pattern, tendency, or notable stance", "..."],
  "notable_cases": [{{"case_name": "...", "summary": "one sentence on the case and the outcome or opinion"}}],
  "sources": ["https://...", "https://..."],
  "confidence_note": "1-2 honest sentences on how complete/reliable this profile is, and what is \
inferred versus directly documented"
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
        tendencies=list(data.get("tendencies") or []),
        notable_cases=list(data.get("notable_cases") or []),
        sources=list(data.get("sources") or []),
        confidence_note=data.get("confidence_note", "") or "",
        auto_researched=True,
        found=bool(data.get("found", True)),
    )
    return save_profile(profile)
