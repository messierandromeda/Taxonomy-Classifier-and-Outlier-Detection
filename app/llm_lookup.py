import json
import pandas as pd
from openai import AsyncOpenAI

from .config import (
    log, OPENAI_API_KEY, OLLAMA_BASE_URL,
    OPENAI_MODEL, OLLAMA_MODEL, TAXONOMY_PATH,
)
from .models import CLCMatch
from .prompts import write_prompt

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

    prompt = write_prompt(TAXONOMY_REFERENCE)

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {'role': 'system', 'content': prompt},
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
    
    if len(code) > 3:
        code = code[-3:]
    
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