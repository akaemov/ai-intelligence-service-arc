"""Verify factual excerpts; external text is never interpreted as instructions."""
import re
from src.models import redact

def verify(observation,raw):
    observation.validate()
    evidence=redact(re.sub(r'\s+',' ',raw['title']).strip())[:280]
    if observation.short_evidence_excerpt!=evidence:
        raise ValueError('Excerpt does not match source fact')
    if observation.factual_summary!=observation.short_evidence_excerpt:
        raise ValueError('Unverified factual summary')
    if observation.signal_type=='A' and observation.source_type=='procurement' and observation.procurement_status!='active':
        raise ValueError('Unverified procurement status')
    return observation
