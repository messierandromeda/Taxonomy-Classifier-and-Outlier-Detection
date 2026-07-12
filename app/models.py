from pydantic import BaseModel, Field
from typing import Optional

class TextRequest(BaseModel):
    text: str = 'Germany: Schleswig-Holstein. Hamburg-Lehmsal, Ostrand des Wittmoores, Ericeetum. 1962-10-27, Leg.: Fr. [Frahm] 965.'
    use_ollama: bool = False
    models: list = ['gpt-4o-mini']
    reps: int = 1

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

class CLCMatch(BaseModel):
    code: str = ''
    name: str = ''
    confidence: Optional[float] = None
    reason: str = ''
    input: str = ''
    model: str = ''
    field: str = ''

class TestModels(BaseModel):
    model: str = ''
    cost: float = 0
    prob_code: str = ''
    output: list[CLCMatch] = Field(default_factory=list)

class ClassifierResult(BaseModel):
    id: str    
    taxon: TaxonMatch = TaxonMatch()
    clc: CLCMatch = CLCMatch()
    error: str = ''

    def to_row(self) -> dict:
        return {
            'id': self.id,
            **{f'clc_{k}': v for k, v in self.clc.model_dump().items()},
            **{f'taxon_{k}': v for k, v in self.taxon.model_dump().items()},
            'error': self.error,
        }