import json
import re
from typing import Any
import logging
from openai import OpenAI

from app.detectors.base import get_record_id
from app.preprocessing.bgbm_normalizer import normalize_bgbm_record
from app.config import OPENAI_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL, OPENAI_MODEL


class LLMDetector:
    """Performs semantic inconsistency detection using an LLM backend.

    The detector builds a concise JSON prompt from key text fields and sends it
    to the configured Ollama service for semantic analysis.
    """

    method_name = "llm_detector"

    def __init__(
        self,
        text_fields: list[str] | None = None,
        timeout: int = 30,
        use_ollama: bool = True,
    ):
        self.text_fields = text_fields or [
            "scientificName",
            "scientificNameFull",
            "genus",
            "family",
            "country",
            "locality",
            "habitat",
            "fundortUndOeko",
            "collectorNotes",
            "labelText",
            "collectionDateBegin",
            "collectionDateEnd",
            "decimalLatitude",
            "decimalLongitude",
            "semanticText",
        ]

        self.timeout = timeout
        if use_ollama:
            self.client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
            self.model = OLLAMA_MODEL
        else:
            self.client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
            self.model = OPENAI_MODEL

            if self.client is None:
                raise RuntimeError("OPENAI_API_KEY is not set and use_ollama is False")

    def detect(self, records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Run the LLM-based semantic detector on a list of records."""
        results: dict[str, list[dict[str, Any]]] = {}

        logging.info(f"[LLM START] records={len(records)} model={self.model}")

        for index, record in enumerate(records):
            normalized_record = normalize_bgbm_record(record)
            record_id = get_record_id(normalized_record, index)
            logging.info(
                f"[LLM] checking record {index + 1}/{len(records)} "
                f"| record_id={record_id}"
            )

            is_suspicious, explanation, confidence = self._ask_llm(normalized_record)
            logging.info(
                f"[LLM] done record_id={record_id} "
                f"| suspicious={is_suspicious} "
                f"| confidence={confidence}"
            )

            if is_suspicious:
                results.setdefault(record_id, []).append(
                    {
                        "field": ",".join(self.text_fields),
                        "method": self.method_name,
                        "type": "semantic_inconsistency",
                        "severity": "medium" if confidence < 0.85 else "high",
                        "score": confidence,
                        "message": explanation,
                        "value": {
                            field: self._shorten_text(normalized_record.get(field))
                            for field in self.text_fields
                        },
                    }
                )

        logging.info(f"[LLM DONE] flagged_records={len(results)}")
        return results

    def _shorten_text(self, value: Any, max_chars: int = 180) -> Any:
        """Truncate long text values for safe prompt construction and output."""
        if not isinstance(value, str):
            return value

        value = " ".join(value.split())

        if len(value) <= max_chars:
            return value

        return value[:max_chars] + "..."

    def _build_relevant_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Build a reduced record containing only relevant text fields for LLM input."""
        relevant_record = {}

        for field in self.text_fields:
            value = record.get(field)

            if value in [None, ""]:
                continue

            if field in [
                "labelText",
                "collectorNotes",
                "locality",
                "habitat",
                "fundortUndOeko",
                "semanticText",
            ]:
                relevant_record[field] = self._shorten_text(value, max_chars=220)
            else:
                relevant_record[field] = value

        return relevant_record

    def _ask_llm(self, record: dict[str, Any]) -> tuple[bool, str, float]:
        """Send the record prompt to Ollama and parse the semantic inconsistency result."""
        relevant_record = self._build_relevant_record(record)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            relevant_record, ensure_ascii=False, indent=2
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )

            raw = response.choices[0].message.content
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logging.warning("LLM returned invalid JSON for: %s", str(raw)[:80])
                return False, "LLM returned invalid JSON.", 0.0

            parsed = data

            suspicious = bool(parsed.get("suspicious", False))
            reason = str(parsed.get("reason") or "Semantic inconsistency detected.")

            confidence_raw = parsed.get("confidence", 0.75)
            confidence = self._safe_confidence(confidence_raw)

            return suspicious, reason, confidence

        except Exception as exc:
            logging.error(f"[LLM ERROR] {exc}")
            return False, f"LLM check failed: {exc}", 0.0

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract a JSON object from raw model output text.

        Falls back to heuristics if the response is not strictly valid JSON.
        """
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1 and end > start:
            json_candidate = text[start : end + 1]

            try:
                return json.loads(json_candidate)
            except json.JSONDecodeError:
                pass

        lowered = text.lower()

        suspicious_true = (
            '"suspicious": true' in lowered
            or '"suspicious":true' in lowered
            or "suspicious true" in lowered
            or "suspicious: true" in lowered
        )

        reason_match = re.search(
            r'"reason"\s*:\s*"([^"]+)"',
            text,
            re.IGNORECASE | re.DOTALL,
        )

        if suspicious_true:
            return {
                "suspicious": True,
                "confidence": 0.75,
                "reason": (
                    reason_match.group(1).strip()
                    if reason_match
                    else "Semantic inconsistency detected."
                ),
            }

        return {
            "suspicious": False,
            "confidence": 0.0,
            "reason": "No semantic inconsistency detected.",
        }

    @staticmethod
    def _safe_confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.75

        return max(0.0, min(1.0, confidence))


SYSTEM_PROMPT = """
You are a biodiversity and herbarium data-quality analyst.

Analyze ONE specimen record.

Your task is to detect semantic or contextual inconsistencies.

Focus on:

1. Coordinates and geography
- Do latitude and longitude fit the country?
- Do coordinates fit the locality text?
- Are coordinates suspicious for the described place?

2. Country and locality
- Does the locality fit the country?
- Does the locality mention another country or region?

3. Habitat and ecology
- Does FundortUNdOeko / habitat fit the taxon?
- Are habitat terms contradictory?
- Example: marine species in dry mountain forest.

4. Taxonomy
- Do family, genus and scientific name look internally consistent?

5. Free text
- Do Anmerkungen / collectorNotes contain meaningful specimen notes?
- Are notes structurally or semantically strange compared to herbarium records?

6. Dates
- Are collection dates plausible?
- Are begin and end dates suspicious in context?

Important rules:
- Missing values alone are not semantic inconsistencies.
- Historical specimens may have incomplete metadata.
- Be conservative.
- Only flag clearly suspicious combinations.

Confidence Score & Reasoning Rubric:
You must assign a confidence score from 0.0 (not confident) to 1.0 (highly confident) based on the following criteria:

### CONFIDENCE SCORING RULES
You must evaluate the data completeness starting from a high score and degrading downward. If the input data has all columns present and has no missing fields, it belongs in the high tiers (0.6 - 1.0).
Based your scoring on the categories 1-6 mentioned above.

If suspicious = false:
- Score 0.90 to 1.0: Perfect Data. Every single field is present, rich with detail, and the metadata seamlessly aligns without a doubt.
- Score 0.60 to 0.85: Standard Clean Data. All major columns are fully populated and clear. There are no missing columns and no contradictions. (IF THE DATA IS CLEAN AND NOT MISSING COLUMNS, YOU MUST SCORE IT HERE).
- Score 0.30 to 0.55: Vague Data. The fields are populated, but descriptions are extremely brief, leaving room for hidden errors.
- Score 0.0 to 0.25: Empty/Sparse Data. Critical fields are entirely blank, unpopulated, or missing, making the record completely unverifiable.

If suspicious = true:
- Score 0.90 to 1.0: Absolute Impossibility. Clear, definitive, rule-breaking contradiction.
- Score 0.60 to 0.85: Highly Probable Anomaly. Strong conflict between fields.
- Score 0.30 to 0.55: Possible Anomaly. Minor contradiction or historical variation.
- Score 0.0 to 0.25: Unconfirmed Anomaly. Data is too sparse or empty to verify if the anomaly is real.


Output Format:
Evaluate using the full range of the scores. Do not default to 0.0 unless the record completely matches the 0.0-0.2 criteria. If the data is fully populated and clean, you must score it in the higher ranges (0.6 - 1.0).
Return ONLY a valid JSON object. Use the following schema:

{
  "suspicious": boolean,
  "confidence": float,
  "reason": "Detailed justification of your decision and confidence score, directly referencing the rubric criteia."
}
"""
