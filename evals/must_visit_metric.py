import re
import unicodedata

from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase, SingleTurnParams

# Presence alone isn't enough: a multi-day anchor (e.g. a 4-day Sintra palace
# circuit) can be silently compressed into a single day while the venue name
# still technically "appears" in the output. This metric additionally counts
# distinct day/date mentions found near each required keyword and fails if
# that count drops below what the golden case requires.

_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_DASH = r"[\-–—]"

_CAL_RANGE_RE = re.compile(rf"(\d{{1,2}})\s*{_DASH}\s*(\d{{1,2}})\s*({_MONTH})\b", re.IGNORECASE)
_CAL_SINGLE_DM_RE = re.compile(rf"\b(\d{{1,2}})\s*({_MONTH})\b", re.IGNORECASE)
_CAL_SINGLE_MD_RE = re.compile(rf"\b({_MONTH})\s*(\d{{1,2}})\b", re.IGNORECASE)
_DAY_IDX_RANGE_RE = re.compile(rf"\bDay\s*(\d{{1,2}})\s*{_DASH}\s*(\d{{1,2}})\b", re.IGNORECASE)
_DAY_IDX_SINGLE_RE = re.compile(r"\bDay\s*(\d{1,2})\b", re.IGNORECASE)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_MAX_SPAN = 31  # a "range" wider than this is almost certainly not a day span


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.casefold()


def _month_key(month: str) -> str:
    return month[:3].lower()


def _extract_day_tokens(sentence: str) -> set:
    tokens = set()

    for d1, d2, mon in _CAL_RANGE_RE.findall(sentence):
        lo, hi = sorted((int(d1), int(d2)))
        if hi - lo <= _MAX_SPAN:
            for day in range(lo, hi + 1):
                tokens.add(("cal", day, _month_key(mon)))

    for day, mon in _CAL_SINGLE_DM_RE.findall(sentence):
        tokens.add(("cal", int(day), _month_key(mon)))

    for mon, day in _CAL_SINGLE_MD_RE.findall(sentence):
        tokens.add(("cal", int(day), _month_key(mon)))

    for d1, d2 in _DAY_IDX_RANGE_RE.findall(sentence):
        lo, hi = sorted((int(d1), int(d2)))
        if hi - lo <= _MAX_SPAN:
            for day in range(lo, hi + 1):
                tokens.add(("idx", day))

    for day in _DAY_IDX_SINGLE_RE.findall(sentence):
        tokens.add(("idx", int(day)))

    return tokens


class MustVisitMetric(BaseMetric):
    """Deterministic (non-LLM) guardrail for Andanzas' Must-Visit exemption.

    Fails unless every keyword in `keywords` appears in the output AND those
    keywords are discussed across at least `required_min_distinct_days`
    distinct day/date mentions, so a compressed multi-day anchor can't pass
    just because the venue name is still present somewhere in the text.
    """

    def __init__(self, keywords, required_min_distinct_days: int = 1, threshold: float = 1.0):
        self.keywords = [keywords] if isinstance(keywords, str) else list(keywords)
        self.required_min_distinct_days = required_min_distinct_days
        self.threshold = threshold
        self._required_params = [SingleTurnParams.ACTUAL_OUTPUT]

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        output = test_case.actual_output or ""
        normalized_output = _normalize(output)

        missing = [kw for kw in self.keywords if _normalize(kw) not in normalized_output]
        if missing:
            self.score = 0.0
            self.reason = f"Missing must-visit keyword(s): {', '.join(missing)}."
            self.success = self.is_successful()
            return self.score

        day_tokens = set()
        for sentence in _SENTENCE_SPLIT_RE.split(output):
            normalized_sentence = _normalize(sentence)
            if any(_normalize(kw) in normalized_sentence for kw in self.keywords):
                day_tokens |= _extract_day_tokens(sentence)

        distinct_days = len(day_tokens)
        if distinct_days < self.required_min_distinct_days:
            self.score = 0.0
            self.reason = (
                f"Must-visit keyword(s) present ({', '.join(self.keywords)}), but only "
                f"{distinct_days} distinct day/date mention(s) found nearby "
                f"(need >= {self.required_min_distinct_days}) — the anchor may have been "
                f"compressed. Tokens found: {sorted(day_tokens)}"
            )
            self.success = self.is_successful()
            return self.score

        self.score = 1.0
        self.reason = (
            f"Must-visit keyword(s) present ({', '.join(self.keywords)}) across "
            f"{distinct_days} distinct day/date mention(s) "
            f"(>= {self.required_min_distinct_days} required)."
        )
        self.success = self.is_successful()
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case, *args, **kwargs)

    @property
    def __name__(self):
        return "Must-Visit Preservation"
