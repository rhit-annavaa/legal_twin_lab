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

        def _tag(source):
            return f"[source: {source}]" if source else "[UNVERIFIED — model-generated, no cited source]"

        tendency_lines = []
        for t in p.tendencies:
            text = t.get("text", "") if isinstance(t, dict) else str(t)
            src = t.get("source") if isinstance(t, dict) else None
            if text:
                tendency_lines.append(f"- {text} {_tag(src)}")
        tendencies = "\n".join(tendency_lines) or "- None specifically documented."

        case_lines = []
        for c in p.notable_cases:
            case_lines.append(f"- {c.get('case_name', '')}: {c.get('summary', '')} {_tag(c.get('source'))}")
        cases = "\n".join(case_lines) or "- None specifically documented."

        sources = "\n".join(f"- {s}" for s in p.sources) or "- None on file."
        manual = (p.manual_notes or "").strip() or "None."

        return f"""{SIMULATION_FRAME}

YOUR ROLE IN THIS SIMULATION: {self.role_label}
YOU ARE MODELING: {p.name}

PUBLIC-RECORD PROFILE
Bio: {p.bio or "Not available."}
Documented tendencies / notable stances (each tagged with its source, or UNVERIFIED if none was found):
{tendencies}
Notable cases or opinions on record (same tagging):
{cases}
Sources consulted during research:
{sources}
Research confidence note: {p.confidence_note or "N/A"}

Treat items tagged [source: ...] as your strongest documented grounding. Treat items tagged \
UNVERIFIED as plausible background color at most — a reasonable inference, not a confirmed fact \
about this real individual — and never present an UNVERIFIED item to the room as if it were \
documented history.

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


JURY_SYSTEM_PROMPT = """This is a confidential, INTERNAL legal-strategy SIMULATION exercise. You \
are modeling a lay jury deciding the facts of a hypothetical or test civil matter. You are not \
lawyers and have no persona to research — you are an ordinary panel of jurors applying common \
sense and the preponderance-of-the-evidence standard (unless told otherwise) to what was actually \
argued in the transcript below.

CRITICAL: real juries return findings, not opinions. You answer the verdict form questions you are \
given and NOTHING else. Do not explain your reasoning, do not write a narrative, do not editorialize \
about either side. Respond with ONLY a JSON object mapping each question id to its answer — no \
markdown fences, no prose before or after."""


class JuryPanel:
    """A generic jury: unlike PersonaAgent, it is not grounded in any named real person's public
    record — it exists only to answer the specific verdict-form questions the judge prepares, and
    is deliberately prompted to produce findings (checkbox/number answers) rather than reasoning."""

    def __init__(self, model: str):
        self.model = model

    def deliberate(self, verdict_questions: list, transcript_so_far: str) -> dict:
        user_content = (
            f"TRIAL TRANSCRIPT:\n{transcript_so_far}\n\n"
            f"VERDICT FORM QUESTIONS (answer every one, by id):\n{json.dumps(verdict_questions, indent=2)}\n\n"
            "Respond with ONLY a JSON object mapping each question's \"id\" to your answer. For "
            "yes_no questions answer exactly \"yes\" or \"no\". For amount questions answer with a "
            "dollar figure like \"$450,000\" (or \"$0\" if none is owed). No reasoning, no narrative."
        )
        resp = client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=JURY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text = _extract_text(resp)
        try:
            return _parse_json_loose(text)
        except Exception:
            return {"_raw": text}
