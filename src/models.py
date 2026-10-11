from dataclasses import dataclass, asdict, fields
from datetime import datetime
from typing import Literal
import hashlib
import math
import types
from typing import get_type_hints, get_origin, get_args
import re
from urllib.parse import urlsplit

Signal = Literal['A', 'B', 'C', 'D', 'E', 'F']

@dataclass
class Observation:
    observation_id: str
    run_id: str
    source_name: str
    source_type: str
    source_url: str
    canonical_url: str
    title: str
    published_at: str | None
    collected_at: str
    original_language: str | None
    region: str | None
    city_or_district: str | None
    geography_evidence: str | None
    organization_name: str | None
    customer_segment: str | None
    industry: str | None
    service_category: str | None
    signal_type: Signal
    customer_problem: str | None
    requested_service: str | None
    explicit_budget: float | None
    currency: str | None
    budget_basis: str | None
    price_type: str | None
    procurement_status: str | None
    short_evidence_excerpt: str
    factual_summary: str
    analyst_interpretation: str | None
    confidence_level: str
    confidence_reason: str
    content_hash: str
    duplicate_group_id: str | None
    limitations: list[str]
    signal_subtype: str | None = None
    survey: dict | None = None
    regional_eligible: bool = False
    country: str | None = None
    federal_district: str | None = None
    customer_region: str | None = None
    customer_city: str | None = None
    execution_geography: str | None = None
    target_market_geography: str | None = None
    contractor_search_geography: str | None = None
    remote_delivery: bool | None = None
    organization_size: str | None = None
    geography_details: dict | None = None
    federal_eligible: bool = False
    event_id: str | None = None
    requirements: str | None = None
    dictionary_version: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    def validate(self):
        for name, hint in get_type_hints(type(self)).items():
            value=getattr(self,name)
            origin=get_origin(hint)
            if origin is Literal:
                valid=value in get_args(hint)
            elif origin is types.UnionType:
                valid=any(value is None if t is type(None) else isinstance(value,t) if t in (str,float,int,bool,dict) else False for t in get_args(hint))
            elif origin is list:
                valid=isinstance(value,list) and all(isinstance(v,str) for v in value)
            else:valid=isinstance(value,hint)
            if not valid:raise ValueError('Invalid field type: '+name)
        for amount in (self.budget_min,self.budget_max):
            if amount is not None and (not math.isfinite(amount) or amount<0 or not self.budget_basis or not self.price_type):raise ValueError('Invalid budget range')
        if self.budget_min is not None and self.budget_max is not None and self.budget_min>self.budget_max:raise ValueError('Reversed budget range')
        if self.explicit_budget is not None and not math.isfinite(self.explicit_budget):raise ValueError('Nonfinite budget')
        if self.signal_type not in 'ABCDEF'  or len(self.signal_type) != 1:
            raise ValueError('invalid signal')
        for key in ('source_url', 'canonical_url'):
            u = urlsplit(getattr(self, key))
            if u.scheme not in ('https', 'http') or not u.hostname or u.username or u.password:
                raise ValueError('invalid public URL')
        datetime.fromisoformat(self.collected_at)
        if self.published_at:
            datetime.fromisoformat(self.published_at)
        if self.explicit_budget is not None and (self.explicit_budget < 0 or not self.budget_basis or not self.price_type):
            raise ValueError('budget requires evidence and type')
        if self.signal_type == 'A' and not self.requested_service:
            raise ValueError('direct demand requires evidence')
        if self.signal_subtype == 'vacancy' and self.signal_type == 'A':
            raise ValueError('vacancy cannot be direct demand')
        if self.regional_eligible and not (self.customer_region and self.country=='Россия' and self.geography_evidence and self.published_at and self.service_category):
            raise ValueError('regional metric lacks provenance')
        if self.federal_eligible and not (self.country=='Россия' and self.geography_evidence and self.published_at and self.service_category):raise ValueError('Federal metric lacks provenance')
        if self.customer_segment not in (None,'business','government','individual'):raise ValueError('Unknown customer segment')
        if len(self.short_evidence_excerpt) > 280:
            raise ValueError('excerpt too long')
        return self
    def dict(self):
        return asdict(self)

PRIVATE = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\w)(?:\+7|8)[\s()-]*(?:\d[\s()-]*){10}(?!\d)|(?<!\w)\+\d[\d ()-]{8,}\d(?!\w)')
def redact(value: str) -> str:
    return PRIVATE.sub('[контакт удалён]', value)
def digest(text: str) -> str:
    return hashlib.sha256(re.sub(r'\s+', ' ', text.lower()).strip().encode()).hexdigest()
