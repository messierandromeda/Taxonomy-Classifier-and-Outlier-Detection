"""
prompt_builder.py — the S1..S5 staircase, composed rather than copy-pasted.

The system prompt is ONE base string + additive modifiers. The user prompt is
built per version. Nothing is duplicated: fixing a typo in the rubric fixes it
for every version, which is what keeps the staircase comparing the same base.

Cumulative versions (each includes everything below it):
  1  reason-before-code        (system: flip JSON key order)
  2  + more information        (user: all locality fields + GBIF taxon, as a blob)
  3  + structured fields       (user: labeled lines instead of a blob)
  4  + species guardrail       (system: don't over-infer from species / cultivated)
  5  + top-3                   (user: Top N: 3; caller still uses matches[0])

v1's base is the EXPERIMENT 1 WINNER (prompt B: land COVER not use, no regional
priors). Do not stack on the losing prompt.
"""

from __future__ import annotations
import pandas as pd

from .taxon_ref import TAXONOMY_REFERENCE
from .models import TaxonMatch
from ..config import LOCALITY_LABELS, FIELD_LABELS, NAME, GENUS, FAMILY, CULTIVATED_FIELD

# --- the single source of truth ----------------------------------------------

_SCHEMA_CODE_FIRST = """{
    "matches": [
        {
        "clc_code": "332",
        "english_name": "Bare Rock",
        "confidence": 0.95,
        "reason": "brief explanation"
        }
    ],
    "summary": "one sentence summary of the land described"
}"""

_SCHEMA_REASON_FIRST = """{
    "matches": [
        {
        "reason": "brief explanation",
        "clc_code": "332",
        "english_name": "Bare Rock",
        "confidence": 0.95
        }
    ],
    "summary": "one sentence summary of the land described"
}"""

_GUARDRAIL = """
SPECIES AND CULTIVATION:
- The collected species can indicate a typical habitat, but the target is the land cover AT THE COLLECTION SITE. If the locality text describes the habitat, prefer it over the species' typical habitat.
- If the input is marked as a cultivated specimen, the plant was grown in a garden or greenhouse and did NOT grow in the surrounding landscape. Ignore the species entirely and classify only from the locality description.
"""


def _base_system() -> str:
    return f"""You are a land cover classification expert.
You have the following detailed land taxonomy (CORINE Land Cover / LBM-DE Level-3 classes):

{TAXONOMY_REFERENCE}

When given a text and a number N, identify the top N best-fitting Level-3 classes.
- Classify the physical land COVER at the collection site — what is physically present on the ground — not the human use or function of the land.
- Always return exactly N matches. Make your best guess even for vague or indirect descriptions.
- Base your judgment on described habitat, vegetation, activities, terrain, and water bodies. A place name with no habitat description is weak evidence — assign a LOW confidence score rather than assuming the land cover typical for that area.
- Only return fewer than N if the text contains absolutely no land-related content.
- Every match MUST use a CLC code from the list above.
{{guardrail}}
CONFIDENCE SCORE CALIBRATION RUBRIC:
You must strictly score each match's confidence value between 0.0 and 1.0 using these objective criteria. Do NOT default to high scores.

[0.90 - 1.00] EXPLICIT MATCH: The text explicitly names the land cover, specific vegetation, or definitive infrastructure matching the CLC definition (e.g., "vineyard", "peat bog", "continuous urban fabric").
[0.70 - 0.89] STRONG INFERENCE: The text describes clear diagnostic activities, structures, or ecosystems unique to that class, but does not explicitly name it (e.g., "milking cows on mountain pastures" -> 231; "harvesting wheat grains" -> 211).
[0.40 - 0.69] PARTIAL/INDIRECT: The text gives some habitat or environmental description that is consistent with this class but is not diagnostic and could fit several classes (e.g., "damp roadside verge" — wet-adjacent but not class-specific).
[0.10 - 0.39] VAGUE/INDIRECT GUESS: The text contains minimal environmental data — e.g. only a place name with no habitat description, or a single weak contextual word. The match is a speculative "best guess".
[0.01 - 0.09] NO RELEVANT CONTENT / FORCED GUESS: The text contains text, but absolutely no land-related, geographic, or environmental content. You are making a blind guess simply to fulfill the requirement of returning N matches.
[0.00] NO CONTENT: The text contains absolutely no land-related context or spatial data.

Respond ONLY with a valid JSON object in this exact format:
{{schema}}"""


def build_system(version: int) -> str:
    """Depends ONLY on version — build once per variant, not per row (keeps the
    OpenAI prompt-prefix cache hitting, since the prefix is then byte-identical)."""
    schema = _SCHEMA_REASON_FIRST if version >= 1 else _SCHEMA_CODE_FIRST
    guardrail = _GUARDRAIL if version >= 4 else ""
    return _base_system().format(schema=schema, guardrail=guardrail)


# --- user prompt -------------------------------------------------------------

def _clean(val) -> str:
    return "" if pd.isna(val) else str(val).strip()


def _is_redundant(val: str, kept: list[str]) -> bool:
    """True if val adds nothing over what's already collected.

    Substring, not equality: this client's `Locality` is `FundortUNdOeko` plus
    appended collector/date/herbarium provenance, so the two are never exactly
    equal — an equality check would let the duplicate through. Compared
    case-insensitively on collapsed whitespace so trivial formatting differences
    don't defeat it.
    """
    norm = ' '.join(val.lower().split())
    for k in kept:
        k_norm = ' '.join(k.lower().split())
        if norm in k_norm or k_norm in norm:
            return True
    return False


def _locality_values(row: pd.Series, all_fields: bool) -> list[tuple[str, str]]:
    """(label, value) for locality fields that carry actual, non-redundant content.

    all_fields=False -> only the highest-priority field (LOCALITY_LABELS is
    priority-ordered), reproducing the v0/v1 single-blob behaviour.
    """
    out: list[tuple[str, str]] = []
    kept: list[str] = []

    for field, label in LOCALITY_LABELS.items():
        val = _clean(row.get(field))
        if not val:
            continue

        if not all_fields:
            return [(label, val)]           # v0/v1: first available field, done

        if _is_redundant(val, kept):        # v2+: skip fields that repeat content
            continue

        out.append((label, val))
        kept.append(val)

    return out


def _taxon_values(taxon: TaxonMatch | None, row: pd.Series) -> list[tuple[str, str]]:
    """Resolved taxon if GBIF is confident, else the raw CSV name. Labels a
    genus-rank hit as 'Genus', not 'Species', so the model doesn't over-infer
    from a name that isn't a species. Never emits the GBIF key."""
    if taxon and taxon.status == "resolved" and taxon.canonical_name:
        label = "Genus" if taxon.rank == "GENUS" else "Species"
        out = [(label, taxon.canonical_name)]
        if taxon.family:
            out.append(("Family", taxon.family))
        return out

    out = []
    for label, key in (("Species", NAME), ("Genus", GENUS), ("Family", FAMILY)):
        val = _clean(row.get(key))
        if val:
            out.append((label, val))
    return out


def is_cultivated(row: pd.Series) -> bool:
    """Derived flag, NOT the raw notes column. Anmerkungen is free text full of
    unrelated remarks; dumping it in gives the model a haystack. What matters is
    the one bit: was this grown in a garden?"""
    note = _clean(row.get(CULTIVATED_FIELD)).lower()
    return any(m in note for m in ("cult.", "cult ", "kult", "garten", "garden"))


def build_user(version: int, row: pd.Series, taxon: TaxonMatch | None = None,
               use_species: bool = True) -> tuple[str, bool]:
    """Returns (user_prompt, has_content).

    has_content is derived from whether any field HAD A VALUE — never from
    `if not text`, because once a label is prepended the string is always
    truthy ("Text: None", "Species: nan") and the empty-row guard dies silently.
    """
    pairs: list[tuple[str, str]] = []
    pairs += _locality_values(row, all_fields=version >= 2)

    cultivated = is_cultivated(row)
    if version >= 2 and use_species and not (version >= 4 and cultivated):
        # v4 drops the species for cultivated specimens: the plant did not grow
        # in that landscape, so its habitat preference is actively misleading.
        pairs += _taxon_values(taxon, row)

    has_content = bool(pairs)
    if not has_content:
        return "", False

    if version >= 3:
        body = "".join(f"{label}: {val}\n" for label, val in pairs)
    else:
        body = "Text: " + " ".join(val for _, val in pairs)

    if version >= 4 and cultivated:
        body += "\nCultivated: yes — grown in a garden, not collected in the wild.\n"

    n = 3 if version >= 5 else 1
    return f"Top N: {n}\n\n{body}", True


# --- registry ----------------------------------------------------------------

MIN_VERSION, MAX_VERSION = 1, 5


def build(version: int, row: pd.Series, taxon: TaxonMatch | None = None,
          use_species: bool = True) -> tuple[str, str, bool]:
    """(system_prompt, user_prompt, has_content). Raises on an unknown version
    rather than silently falling back to a default."""
    if not MIN_VERSION <= version <= MAX_VERSION:
        raise ValueError(f"unknown prompt version {version} (expected {MIN_VERSION}-{MAX_VERSION})")
    user, has_content = build_user(version, row, taxon, use_species)
    return build_system(version), user, has_content


def top_n_for(version: int) -> int:
    return 3 if version >= 5 else 1