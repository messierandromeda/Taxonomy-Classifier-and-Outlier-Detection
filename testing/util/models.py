from typing import Optional
from pydantic import BaseModel

from app.models import TaxonMatch

def _fmt(val, limit=100):
    if isinstance(val, str) and len(val) > limit:
        return repr(val[:limit] + f"… (+{len(val) - limit} more chars)")
    return repr(val)

class TestClassification(BaseModel):
    id: str = ""
    code: str = ""
    name: str = ""
    confidence: Optional[float] = None
    reason: str = ""
    input: str = ""
    model: str = ""
    prompt_variant: str = ""
    top_n: int = 1
    all_matches: list[dict] = []          # populated when top_n > 1 (S4-style)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None
    parse_failure: bool = False
    unknown_code: bool = False
    error: str = ""

    def __repr__(self) -> str:
        parts = [f"{name}={_fmt(getattr(self, name))}"
                 for name in self.model_fields]        # v1: self.__fields__
        return "TestClassification(\n" + ",\n".join(parts) + "\n)"

class TestResult(BaseModel):
    id: str    
    taxon: TaxonMatch = TaxonMatch()
    clc: TestClassification = TestClassification()
    error: str = ''

    def to_row(self) -> dict:
        return {
            'id': self.id,
            **{f'clc_{k}': v for k, v in self.clc.model_dump().items()},
            **{f'taxon_{k}': v for k, v in self.taxon.model_dump().items()},
            'error': self.error,
        }