from pydantic import BaseModel
from typing import Optional

class TaxonMatch(BaseModel):
    identifier: str = ''
    confidence: Optional[float] = None
    status: str = 'unresolved'

class CLCMatch(BaseModel):
    code: int = -1
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

class LandTaxonomyLevel(BaseModel):
    clc_code: int
    english_name: str
    confidence: float

class LandTaxonomyMatch(BaseModel):
    reason: str
    level3: LandTaxonomyLevel

class LandTaxonomyResponse(BaseModel):
    matches: list[LandTaxonomyMatch]
    input_text: str