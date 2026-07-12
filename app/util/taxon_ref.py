import pandas as pd

from ..config import TAXONOMY_PATH

# Taxonomy Reference
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
