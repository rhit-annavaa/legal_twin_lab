import json
import re
from importlib import import_module

# Import dynamically so static analyzers do not require the optional SDK to be
# installed in their analysis environment.
Anthropic = import_module("anthropic").Anthropic

import config
from .profile import Profile

client = Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _extract_text(resp) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()


def _parse_json_loose(text: str) -> dict:
    cleaned = re.sub(r"^```(json)?", "", text.strip(), flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned.strip()).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


SIMULATION_FRAME = """This is a confidential, INTERNAL legal-strategy SIMULATION exercise. You are \
modeling, to the best of available public knowledge, how a specific named legal professional would \
plausibly argue or rule in a hypothetical or test matter. This is a predictive analytical exercise, \
NOT an actual statement, filing, or ruling by the real person, and it will never be represented as \
one. Ground your reasoning in the documented public record below wherever it genuinely applies, \
marking such claims inline as "(per documented record)". Where nothing in the record applies and \
you are relying on general legal knowledge or doctrine instead, reason as a skilled legal \
professional would, without implying it is a verified fact about this specific individual."""


class PersonaAgent:
    def __init__(self, profile: Profile, role_label: str, case_context: str, model: str):
        self.profile = profile
        self.role_label = role_label
        self.case_context = case_context
        self.model = model
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        p = self.profile
        tendencies = "\n".join(f"- {t}" for t in p.tendencies) or "- None specifically documented."
        cases = "\n".join(
            f"- {c.get('case_name', '')}: {c.get('summary', '')}" for c in p.notable_cases
        ) or "- None specifically documented."
        sources = "\n".join(f"- {s}" for s in p.sources) or "- None on file."
        manual = (p.manual_notes or "").strip() or "None."

        return f"""{SIMULATION_FRAME}

YOUR ROLE IN THIS SIMULATION: {self.role_label}
YOU ARE MODELING: {p.name}

PUBLIC-RECORD PROFILE
Bio: {p.bio or "Not available."}
Documented tendencies / notable stances:
{tendencies}
Notable cases or opinions on record:
{cases}
Sources consulted during research:
{sources}
Research confidence note: {p.confidence_note or "N/A"}

USER-PROVIDED NOTES (may supplement or override the above): {manual}

CASE CONTEXT FOR THIS SIMULATION:
{self.case_context}

Speak in first person, in a manner consistent with a skilled legal professional in this role. Keep \
each response focused and realistic in length for the stage of proceeding requested (a few tight \
paragraphs, not an essay). Do not break character to comment on the fact that this is a simulation."""

    def speak(self, instruction: str, transcript_so_far: str, max_tokens: int = 3000) -> str:
        user_content = (
            f"TRANSCRIPT SO FAR:\n{transcript_so_far or '(nothing yet — you are speaking first)'}"
            f"\n\nINSTRUCTION:\n{instruction}"
        )
        resp = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        return _extract_text(resp)

    def speak_json(self, instruction: str, transcript_so_far: str) -> dict:
        user_content = (
            f"TRANSCRIPT SO FAR:\n{transcript_so_far}\n\nINSTRUCTION:\n{instruction}\n\n"
            "Respond with ONLY a valid JSON object — no markdown fences, no extra prose."
        )
        resp = client.messages.create(
            model=self.model,
            max_tokens=1536,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        text = _extract_text(resp)
        try:
            return _parse_json_loose(text)
        except Exception:
            return {"_raw": text}
