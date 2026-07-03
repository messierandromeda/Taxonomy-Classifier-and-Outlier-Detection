import json
import pandas as pd
from openai import AsyncOpenAI

from config import (
    log, OPENAI_API_KEY, OLLAMA_BASE_URL,
    OPENAI_MODEL, OLLAMA_MODEL, TAXONOMY_PATH,
)
from models import CLCMatch

# --- Taxonomy loaded once at import (was the land-taxonomy-api startup block) ---
_df = pd.read_csv(TAXONOMY_PATH, sep=';', encoding='utf-8-sig', dtype=str).fillna('')

TAXONOMY_ENTRIES = [
    {
        'clc_code': r['CLC Code'].strip(),
        'level': r['Level'].strip(),
        'english_name': r['English Name'].strip(),
        'german_name': r['German Name'].strip(),
        'synonyms': r['Synonyms'].strip(),
    }
    for _, r in _df.iterrows()
    if r['English Name'].strip()
]

_by_code = {e['clc_code']: e for e in TAXONOMY_ENTRIES}
_l3 = [e for e in TAXONOMY_ENTRIES if e['level'] == '3']

TAXONOMY_REFERENCE = '\n'.join(
    f"- [CLC {e['clc_code']}] {e['english_name']}"
    + (f" (aka: {e['synonyms']})" if e['synonyms'] else '')
    for e in _l3
)

SYSTEM_PROMPT = f"""You are a land-use classification expert with broad geographic knowledge.
You have the following detailed land taxonomy (CORINE Land Cover / LBM-DE Level-3 classes):

{TAXONOMY_REFERENCE}

When given a text and a number N, identify the top N best-fitting Level-3 classes.
- Always return exactly N matches. Make your best guess even for vague or indirect descriptions.
- Use all contextual clues: named places, described activities, vegetation, terrain, water bodies, etc. Named locations imply the land types typical for that region.
- Only return fewer than N if the text contains absolutely no land-related content.
- Every match MUST use a CLC code from the list above.

CONFIDENCE SCORE CALIBRATION RUBRIC:
You must strictly score each match's confidence value between 0.0 and 1.0 using these objective criteria. Do NOT default to high scores.

[0.90 - 1.00] EXPLICIT MATCH: The text explicitly names the land type, specific vegetation, or definitive infrastructure matching the CLC definition (e.g., "vineyard", "peat bog", "continuous urban fabric").
[0.70 - 0.89] STRONG INFERENCE: The text describes clear diagnostic activities, structures, or ecosystems unique to that class, but does not explicitly name it (e.g., "milking cows on mountain pastures" -> 231; "harvesting wheat grains" -> 211).
[0.40 - 0.69] REGIONAL/CONTEXTUAL PROBABILITY: The land type is not described, but a named geographic location or broad activity implies a strong regional likelihood (e.g., "sampling near downtown Berlin" -> implies an urban fabric class based on geography).
[0.10 - 0.39] VAGUE/INDIRECT GUESS: The text contains minimal environmental data. The match is a speculative "best guess" based on a single weak contextual word or highly indirect clue.
[0.01 - 0.09] NO RELEVANT CONTENT / FORCED GUESS: The text contains text, but absolutely no land-related, geographic, or environmental content. You are making a blind guess simply to fulfill the requirement of returning N matches.
[0.00] NO CONTENT: The text contains absolutely no land-related context or spatial data.

Respond ONLY with a valid JSON object in this exact format:
{{
  "matches": [
    {{
      "clc_code": "332",
      "english_name": "Bare Rock",
      "confidence": 0.95,
      "reason": "brief explanation"
    }}
  ],
  "summary": "one sentence summary of the land described"
}}"""

# --- Clients built once and reused, instead of one per request ---
_openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
_ollama_client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key='ollama')


async def classify_land(text: str, use_ollama: bool, model: str = OPENAI_MODEL) -> CLCMatch:
    """Classify free text into a CLC Level-3 category. Returns an empty CLCMatch
    when there is no usable text or the model gives nothing parseable."""
    if not text or not text.strip():
        return CLCMatch()

    if use_ollama:
        client, model = _ollama_client, OLLAMA_MODEL
    else:
        if _openai_client is None:
            raise RuntimeError('OPENAI_API_KEY is not set and use_ollama is False')
        client = _openai_client

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': f'Top N: 1\n\nText: {text}'},
        ],
        response_format={'type': 'json_object'},
        temperature=0,
    )

    raw = response.choices[0].message.content
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        log.warning('LLM returned invalid JSON for: %s', text[:80])
        return CLCMatch()

    matches = data.get('matches', [])
    if not matches:
        return CLCMatch()

    top = matches[0]
    code = top.get('clc_code', '')
    entry = _by_code.get(code)
    if entry is None:
        log.warning('LLM returned unknown CLC code: %s', code)

    return CLCMatch(
        code=code,
        name=entry['english_name'] if entry else '',   # canonical name, not the LLM's
        confidence=top.get('confidence'),
        reason=top.get('reason', ''),
        input=text,
        model=model,
    )