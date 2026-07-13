''''''

import json
import hashlib
import re

from openai import AsyncOpenAI

from .config import log, OPENAI_API_KEY 
from .util.taxon_ref import _by_code
from .util.models import LLMMatch

_clients: dict[str, AsyncOpenAI] = {}
_warmed: set[str] = set()          # prefix hashes already written to the cache

# Per-model API quirks. Explicit table > prefix matching: prefix checks break on
# every new family (and the SDK does not yet expose capability metadata).
MODEL_PARAMS = {
    'gpt-4.1-nano':  {'temperature': 0},
    'gpt-5-nano':    {'reasoning_effort': 'minimal'},   # no 'none' option -> temp unavailable
    'gpt-5.4-nano':  {'temperature': 0, 'reasoning_effort': 'none'},
    'gpt-5.4-mini':  {'temperature': 0, 'reasoning_effort': 'none'},
    'gpt-5.6-terra': {'temperature': 0, 'reasoning_effort': 'none'},
}

def _client_for(model: str) -> AsyncOpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError('OPENAI_API_KEY is not set')
    if 'openai' not in _clients:
        _clients['openai'] = AsyncOpenAI(api_key=OPENAI_API_KEY, max_retries=8)
    return _clients['openai']


def cache_key_for(model: str, system_prompt: str) -> str:
    '''Stable routing key for one (model, system prompt) pair. Combined with the
    prefix hash server-side, so identical prefixes land on the same machine.'''
    h = hashlib.sha1(system_prompt.encode()).hexdigest()[:12]
    return f'clc-{model}-{h}'


async def warm_cache(model: str, system_prompt: str) -> bool:
    '''One throwaway call to write this system prompt into OpenAI's prefix cache.

    A cache entry is only written by a request that COMPLETES, so a burst of N
    parallel rows against a cold cache is N guaranteed misses. Calling this once
    before the burst turns those into hits.

    Idempotent: safe to call at the top of every rep. Returns True if a call was
    actually made. Never raises — a failed warmup costs hits, not the run.
    '''
    key = cache_key_for(model, system_prompt)
    if key in _warmed:
        return False

    client = _client_for(model)
    try:
        await client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': system_prompt},   # the prefix — identical
                {'role': 'user', 'content': 'Top N: 1\n\nText: warmup'},
            ],
            response_format={'type': 'json_object'},
            max_completion_tokens=16,      # we throw the answer away; don't pay for it
            prompt_cache_key=key,
            **MODEL_PARAMS.get(model, {}),
        )
    except Exception as exc:
        log.warning('cache warmup failed (model=%s): %s', model, exc)
        return False

    _warmed.add(key)
    log.info('warmed prompt cache: %s (%d chars)', key, len(system_prompt))
    return True


def _code_from(raw_code: str) -> str:
    m = re.search(r'\d{3}', raw_code or '')
    return m.group(0) if m else ''


async def classify_land(
    id: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    prompt_variant: str,
    top_n: int = 1,
) -> LLMMatch:
    result = LLMMatch(
        id=id, input=user_prompt, model=model,
        prompt_variant=prompt_variant, top_n=top_n,
    )


    client = _client_for(model)

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        response_format={'type': 'json_object'},
        prompt_cache_key=cache_key_for(model, system_prompt),
        **MODEL_PARAMS.get(model, {}),
    )

    usage = response.usage
    if usage:
        result.prompt_tokens = usage.prompt_tokens
        result.completion_tokens = usage.completion_tokens
        details = getattr(usage, 'prompt_tokens_details', None)
        result.cached_tokens = getattr(details, 'cached_tokens', None) if details else None

    raw = response.choices[0].message.content
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        log.warning('LLM returned invalid JSON (model=%s, variant=%s): %s',
                    model, prompt_variant, user_prompt[:80])
        result.parse_failure = True
        return result

    matches = data.get('matches', [])
    if not matches:
        return result

    result.all_matches = matches
    top = matches[0]
    code = _code_from(top.get('clc_code', ''))
    entry = _by_code.get(code)
    if code and entry is None:
        log.warning('LLM returned unknown CLC code: %s', code)
        result.unknown_code = True

    result.code = code
    result.name = entry['english_name'] if entry else ''
    result.confidence = top.get('confidence')
    result.reason = top.get('reason', '')

    return result