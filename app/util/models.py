from pydantic import BaseModel, Field
from typing import Optional

class TaxonMatch(BaseModel):
    key: str = ''
    link: str = ''
    confidence: Optional[float] = None
    status: str = 'unresolved'
    canonical_name: str = ''
    rank: str = ''
    family: str = ''
    match_type: str = ''
    is_synonym: bool = False
    accepted_status: str = ''

class LLMMatch(BaseModel):
    code: str = ''
    name: str = ''
    confidence: Optional[float] = None
    reason: str = ''
    input: str = ''
    model: str = ''
    top_n: int = 3
    all_matches: list[dict] = []
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None
    parse_failure: bool = False
    unknown_code: bool = False
    error: str = ''

class TestModels(BaseModel):
    model: str = ''
    cost: float = 0
    prob_code: str = ''
    output: list[LLMMatch] = Field(default_factory=list)

class ClassifierResult(BaseModel):
    id: str    
    taxon: TaxonMatch = Field(default_factory=TaxonMatch)
    llm: LLMMatch = Field(default_factory=LLMMatch)
    error: str = ''
    
    def to_row(self) -> dict:
        return {
            'id': self.id,
            **{f'llm_{k}': v for k, v in self.llm.model_dump().items()},
            **{f'taxon_{k}': v for k, v in self.taxon.model_dump().items()},
            'error': self.error,
        }

class TextRequest(BaseModel):
    text: str = 'Germany: Schleswig-Holstein. Hamburg-Lehmsal, Ostrand des Wittmoores, Ericeetum. 1962-10-27, Leg.: Fr. [Frahm] 965.'
    # use_ollama: bool = False
    models: list = ['gpt-4o-mini']
    reps: int = 1

class ClassifyCSVRequest(BaseModel):
    model: str = 'gpt-5.4-mini'
