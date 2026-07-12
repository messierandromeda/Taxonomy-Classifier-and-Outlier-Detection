from app.util.taxon_ref import TAXONOMY_REFERENCE

def build_a() -> str:
    prompt = f"""You are a land-use classification expert with broad geographic knowledge.
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

    return prompt


def build_b() -> str:
    prompt = f"""You are a land cover classification expert.
    You have the following detailed land taxonomy (CORINE Land Cover / LBM-DE Level-3 classes):

    {TAXONOMY_REFERENCE}

    When given a text and a number N, identify the top N best-fitting Level-3 classes.
    - Classify the physical land COVER at the collection site — what is physically present on the ground — not the human use or function of the land.
    - Always return exactly N matches. Make your best guess even for vague or indirect descriptions.
    - Base your judgment on described habitat, vegetation, activities, terrain, and water bodies. A place name with no habitat description is weak evidence — assign a LOW confidence score rather than assuming the land cover typical for that area.
    - Only return fewer than N if the text contains absolutely no land-related content.
    - Every match MUST use a CLC code from the list above.

    CONFIDENCE SCORE CALIBRATION RUBRIC:
    You must strictly score each match's confidence value between 0.0 and 1.0 using these objective criteria. Do NOT default to high scores.

    [0.90 - 1.00] EXPLICIT MATCH: The text explicitly names the land cover, specific vegetation, or definitive infrastructure matching the CLC definition (e.g., "vineyard", "peat bog", "continuous urban fabric").
    [0.70 - 0.89] STRONG INFERENCE: The text describes clear diagnostic activities, structures, or ecosystems unique to that class, but does not explicitly name it (e.g., "milking cows on mountain pastures" -> 231; "harvesting wheat grains" -> 211).
    [0.40 - 0.69] PARTIAL/INDIRECT: The text gives some habitat or environmental description that is consistent with this class but is not diagnostic and could fit several classes (e.g., "damp roadside verge" — wet-adjacent but not class-specific).
    [0.10 - 0.39] VAGUE/INDIRECT GUESS: The text contains minimal environmental data — e.g. only a place name with no habitat description, or a single weak contextual word. The match is a speculative "best guess".
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

    return prompt