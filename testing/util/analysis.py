"""
analysis.py — shared analysis logic for experiments 1-4.

Imported by every notebook. NOT copy-pasted between them: the copy-pasted version
of cells_of() drifted and then crashed on rows where every rep failed (401s), and
silently mis-computed consistency by dividing by total reps instead of *successful*
reps — which penalised whichever model had more failures, corrupting the very
comparison exp 3 exists to make.

WHAT THIS MODULE ENCODES (learned the hard way):

  * consistency divides by SUCCESSFUL reps, not total reps
  * rows where every rep failed produce a row with NaNs, not an IndexError
  * failures are counted and surfaced (n_failed), never silently absorbed
  * CLC agreement is computed but is NOT the deciding metric — see the note on
    agreement() below
"""

from __future__ import annotations
import ast
import pandas as pd

# --- pricing (per 1M tokens) — VERIFY against the live pricing page ------------
PRICES = {
    'gpt-4.1-nano':  {'input': 0.10, 'output': 0.40},
    'gpt-5-nano':    {'input': 0.05, 'output': 0.40},
    'gpt-5.4-nano':  {'input': 0.20, 'output': 1.25},
    'gpt-5.4-mini':  {'input': 0.75, 'output': 4.50},
    'gpt-5.6-terra': {'input': 2.50, 'output': 15.00},
}
CACHED_DISCOUNT = 0.10          # cached input bills at ~1/10th


def cost_of(prompt_tokens, completion_tokens, cached_tokens, model) -> float | None:
    p = PRICES.get(model)
    if p is None:
        return None
    cached = cached_tokens or 0
    uncached = max(prompt_tokens - cached, 0)
    return (uncached * p['input']
            + cached * p['input'] * CACHED_DISCOUNT
            + completion_tokens * p['output']) / 1_000_000


# --- reference ----------------------------------------------------------------

def load_reference(path: str) -> dict[str, str]:
    """row_id -> CLC code. Only coordinate-bearing rows are in this file."""
    clc = pd.read_csv(path, dtype={'row_id': str})
    clc['landcover'] = clc['landcover'].astype(str).str.split('.').str[0]
    return clc.set_index('row_id')['landcover'].to_dict()


def agreement(code, ref, level: int) -> bool | None:
    """Hierarchical CLC agreement at L1/L2/L3.

    !! READ THIS BEFORE USING IT AS A SCORE !!
    Exp 2 established that agreement CANNOT rank prompts or models. On the 102-row
    working set, agree_L1 was WORSE on `unambiguous` rows (0.20) than on `thin`
    rows (0.34). That inversion is the sub-MMU effect: rows with specific habitat
    text describe a microhabitat CLC's 25 ha pixel cannot resolve, while thin rows
    push the model toward guessing the regional dominant cover — which is exactly
    what CLC measures. Agreement therefore REWARDS a model for ignoring the text. 

    Exp 3 confirmed this independently: on 9 of 12 rows where nano disagreed with CLC, Terra returned the identical code. 
    Two independent models converging against the map = the map is wrong there, not the model.
    """
    if not ref or pd.isna(ref) or not code or pd.isna(code):
        return None
    return str(code)[:level] == str(ref)[:level]


# --- the core aggregation -----------------------------------------------------

def cells_of(raw: pd.DataFrame, ref: dict[str, str] | None = None) -> pd.DataFrame:
    """Long per-call rows -> one cell per row_id.

    Handles the failure cases that broke the copy-pasted version:
      - a row where EVERY rep failed (all clc_code NaN) yields NaNs, not IndexError
      - consistency divides by successful reps, so a model with more failures is
        not silently penalised
    """
    out = []
    for rid, g in raw.groupby('id'):
        counts = g['clc_code'].value_counts()          # drops NaN
        n_failed = int(g['clc_code'].isna().sum())

        rec = {
            'id': rid,
            'difficulty': g['difficulty'].iloc[0] if 'difficulty' in g else None,
            'n_reps': len(g),
            'n_failed': n_failed,
            'parse_fail': g['clc_parse_failure'].mean() if 'clc_parse_failure' in g else 0.0,
            'unknown_code': g['clc_unknown_code'].mean() if 'clc_unknown_code' in g else 0.0,
        }

        if counts.empty:                                # every rep failed
            rec.update(modal_code=None, consistency=None, n_distinct=0, mean_conf=None)
        else:
            rec.update(
                modal_code=counts.index[0],
                consistency=counts.iloc[0] / counts.sum(),   # successful reps only
                n_distinct=len(counts),
                mean_conf=g['clc_confidence'].mean(),
            )

        if ref is not None:
            r = ref.get(rid)
            rec['ref'] = r
            for lv in (1, 2, 3):
                rec[f'agree_L{lv}'] = agreement(rec['modal_code'], r, lv)

        out.append(rec)

    return pd.DataFrame(out)


# --- guards -------------------------------------------------------------------

def guard(raw: pd.DataFrame, expect_variant: str | None = None,
          expect_model: str | None = None, label: str = '') -> None:
    """Every bug in this project was a variant/version that never reached the API.
    These asserts catch that class outright — run them before reading any number."""
    assert raw['id'].notna().all(), f'{label}: NaN id -> merges will cross-join'

    if expect_variant is not None:
        got = list(raw['clc_prompt_variant'].unique())
        assert got == [expect_variant], f'{label}: expected {expect_variant}, ran {got}'

    if expect_model is not None:
        got = list(raw['clc_model'].unique())
        assert got == [expect_model], f'{label}: expected {expect_model}, ran {got}'

    n_failed = raw['clc_code'].isna().sum()
    if n_failed:
        print(f'  ⚠ {label}: {n_failed}/{len(raw)} calls failed '
              f'({raw.groupby("id")["clc_code"].apply(lambda s: s.isna().all()).sum()} rows fully lost)')


def token_guard(raw: pd.DataFrame, by: str = 'version') -> pd.Series:
    """Prompts that differ MUST differ in token count. Identical counts across
    rungs is definitionally impossible unless the same prompt ran twice."""
    tok = raw.groupby(by)['clc_prompt_tokens'].mean().round(1)
    print('mean prompt tokens by', by, '(must differ where prompts differ):')
    print(tok)
    return tok


# --- calibration --------------------------------------------------------------

def calibration(cells: pd.DataFrame, restrict_to='unambiguous_candidate') -> pd.DataFrame:
    """Does confidence track correctness?

    THE decisive metric. The production resolver routes on confidence (low -> trust
    GEE, high -> trust the LLM); if confidence is noise, that routing is worthless.
    Restricted to unambiguous rows because that's where CLC is least distorted by
    sub-MMU — the one slice where agreement means something.

    A calibrated model shows agree RISING low -> mid -> high.
    Flat or inverted = confidence is noise. (Exp 3: gpt-5-nano scored 0.714 at low
    confidence and 0.625 at high — anti-correlated, and disqualifying.)
    """
    u = cells[cells['difficulty'] == restrict_to].copy() if restrict_to else cells.copy()
    u = u[u['ref'].notna() & u['mean_conf'].notna()]
    if u.empty:
        return pd.DataFrame()
    u['band'] = pd.cut(u['mean_conf'], [0, 0.09, 0.39, 0.69, 0.89, 1.0], labels=['very low', 'low', 'mid', 'high', 'very high'])
    return u.groupby('band', observed=True)['agree_L1'].agg(['mean', 'count']).round(3)


def flip_rate(cells_a: pd.DataFrame, cells_b: pd.DataFrame) -> dict:
    """How many modal codes change between two prompt configs.

    Exp 3 found this is 48-75% across EVERY model on a trivial key-reorder. That is
    not a small-model weakness — it is universal, and it is a serious caveat on the
    whole approach: the answer depends heavily on incidental prompt phrasing.
    """
    m = (cells_a.set_index('id')[['modal_code']]
         .join(cells_b.set_index('id')[['modal_code']], lsuffix='_a', rsuffix='_b'))
    m = m.dropna()
    flipped = int((m['modal_code_a'] != m['modal_code_b']).sum())
    return {'codes_flipped': flipped, 'n': len(m),
            'flip_rate': round(flipped / len(m), 3) if len(m) else None}


# --- top-3 (v5) ---------------------------------------------------------------

def parse_matches(s):
    """clc_all_matches is a Python repr (single quotes), NOT JSON."""
    try:
        return ast.literal_eval(s) if isinstance(s, str) else []
    except (ValueError, SyntaxError):
        return []


def topn_signals(raw: pd.DataFrame, ref: dict[str, str]) -> pd.DataFrame:
    """Ambiguity signals from the v5 top-3.

    NOTE the exp-2 finding, which inverts the obvious rule: the confidence GAP is
    LARGEST on boundary rows (0.290) and SMALLEST on thin rows (0.144). So a small
    gap does NOT mean "ambiguous habitat" — it means "no signal in the text, I'm
    spreading my bets". Use L1-SPREAD across the top-3 for genuine ambiguity: three
    codes in different L1 families = a real boundary case; three codes within one
    L1 = confident about the family, unsure of the subclass.
    """
    d = raw.copy()
    d['matches'] = d['clc_all_matches'].apply(parse_matches)
    d['n_returned'] = d['matches'].apply(len)

    def gap(ms):
        if len(ms) < 2:
            return None
        return (ms[0].get('confidence') or 0) - (ms[1].get('confidence') or 0)

    def l1_spread(ms):
        return len({str(m.get('clc_code', ''))[:1] for m in ms if m.get('clc_code')})

    def ref_in_topn(row):
        r = ref.get(row['id'])
        ms = row['matches']
        if not r or len(ms) < 2:
            return None
        top = str(ms[0].get('clc_code', ''))
        others = [str(m.get('clc_code', '')) for m in ms[1:]]
        return top != r and r in others          # the map's answer was the runner-up

    d['conf_gap'] = d['matches'].apply(gap)
    d['l1_spread'] = d['matches'].apply(l1_spread)     # 1 = same family, 2-3 = real ambiguity
    d['ref_rescued'] = d.apply(ref_in_topn, axis=1)
    return d