from pydantic import BaseModel
from typing import Optional

class TextRequest(BaseModel):
    text: str
    use_ollama: bool = False

class TaxonMatch(BaseModel):
    identifier: str = ''
    confidence: Optional[float] = None
    status: str = 'unresolved'

class CLCMatch(BaseModel):
    code: str = ''
    name: str = ''
    confidence: Optional[float] = None
    reason: str = ''
    input: str = ''
    source: str = ''
    field: str = ''

class HerbariumRecord(BaseModel):
    HerbariumID: str
    FullNameCache: str = ''
    Genus: str = ''
    Family: str = ''
    Locality: str = ''
    FundortUNdOeko: str = ''

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