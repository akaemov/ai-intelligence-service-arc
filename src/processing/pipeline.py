import json
import re
import uuid
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from src.models import Observation,digest,redact

DICTIONARY=json.loads((Path(__file__).resolve().parents[2]/'config/dictionary.json').read_text())
LEXICON=DICTIONARY['services']
INTENT=re.compile('|'.join(re.escape(x) for x in DICTIONARY['intent']),re.I)
OFFER=re.compile(r'предлагаем|наши услуги|оказываем|наше агентство|закажите у нас',re.I)

def canonical(url):
    u=urlsplit(url)
    query=[(k,v) for k,v in parse_qsl(u.query) if not k.startswith('utm_') and k not in ('fbclid','yclid','erid')]
    return urlunsplit((u.scheme,u.netloc.lower(),u.path or '/',urlencode(sorted(query)),''))

def classify(text,kind,request_verified=False):
    if kind=='vacancies':return 'C','vacancy'
    if OFFER.search(text):return 'D',None
    if request_verified:return 'A',None
    if kind=='media':return 'E',None
    if INTENT.search(text):return 'A',None
    if any(p in text.lower() for p in DICTIONARY['problems']):return 'C',None
    return 'E',None

def normalize(raw,source,run_id,config,now):
    title=re.sub(r'\s+',' ',raw['title']).strip()
    source_text=title+' '+raw.get('evidence_text','')
    category=next((k for k,terms in LEXICON.items() if any(t in source_text.lower() for t in terms)),None)
    signal,subtype=classify(source_text,source['category'],raw.get('request_verified',False))
    status=raw.get('procurement_status')
    if source['category']=='procurement' and status=='active' and raw.get('request_verified') and not OFFER.search(source_text):signal='A'
    if source['category']=='procurement' and (status!='active' or not raw.get('request_verified')) and signal=='A':signal='E'
    if not category:signal='F'
    geo=raw.get('geography_evidence');country=raw.get('country')
    customer_region=raw.get('customer_region');customer_city=raw.get('customer_city')
    # Compatibility only for explicitly verified collector fields, never city words in text.
    if raw.get('verified_region') and geo:
        customer_region=raw['verified_region'];customer_city=raw.get('city');country='Россия'
    if not geo:country=None;customer_region=None;customer_city=None
    published=raw.get('published_at')
    limitations=['Автоматическая классификация; перед коммерческим решением проверьте первоисточник']
    if raw.get('date_basis'):limitations.append('Основание даты: '+raw['date_basis'])
    if 'erid=' in raw['url']:limitations.append('Рекламная маркировка: материал не подтверждает покупательское намерение')
    if not published:limitations.append('Дата неизвестна; материал исключён из показателей периода')
    if country!='Россия':limitations.append('Связь с российским рынком не подтверждена; вне федеральных показателей')
    if not customer_region:limitations.append('Регион заказчика не установлен; не включён в региональные показатели')
    if subtype=='vacancy':limitations.append('Вакансия — потребность в компетенциях, не заказ подрядчику; зарплата не бюджет услуги')
    language=raw.get('language','ru')
    if language!='ru':limitations.append('Качественный перевод не подключён')
    in_period=False
    if published:
        dt=datetime.fromisoformat(published)
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        in_period=0<=(now-dt).total_seconds()/86400<=config['days']
        if not in_period:limitations.append('Вне исследуемого периода')
    selected=not config.get('regions') or customer_region in config['regions']
    selected=selected and (not config.get('cities') or customer_city in config['cities'])
    sector=not config.get('industries') or raw.get('industry') in config['industries']
    scope_ok=selected and sector
    eligible=country=='Россия' and bool(geo) and category in config['services'] and in_period and language=='ru' and scope_ok
    if config.get('regions') and not selected:limitations.append('Не относится к выбранной географии')
    if not sector:limitations.append('Отрасль не подтверждена или вне выбранного фильтра')
    excerpt=redact(re.sub(r'\s+',' ',raw.get('evidence_text') or title).strip())[:280]
    url=canonical(raw['url'])
    budget=raw.get('explicit_budget')
    if budget is not None and (not raw.get('budget_basis') or not raw.get('price_type')):budget=None
    problem=next((p for p in DICTIONARY['problems'] if p in source_text.lower()),None)
    item=Observation(
      observation_id=str(uuid.uuid5(uuid.NAMESPACE_URL,raw.get('event_id') or url)),run_id=run_id,
      source_name=source['name'],source_type=source['category'],source_url=url,canonical_url=url,title=redact(title)[:400],
      published_at=published,collected_at=now.isoformat(),original_language=language,region=customer_region,city_or_district=customer_city,
      geography_evidence=redact(geo) if geo else None,organization_name=raw.get('organization_name'),
      customer_segment=raw.get('customer_segment'),industry=raw.get('industry'),service_category=category,signal_type=signal,
      customer_problem=problem,requested_service=redact(title)[:280] if signal=='A' else None,
      explicit_budget=float(budget) if budget is not None else None,currency=raw.get('currency') if budget is not None or raw.get('budget_min') is not None else None,
      budget_basis=redact(raw['budget_basis']) if raw.get('budget_basis') else None,price_type=raw.get('price_type') if raw.get('budget_basis') else None,
      procurement_status=status,short_evidence_excerpt=excerpt,factual_summary=excerpt,analyst_interpretation=None,
      confidence_level='medium' if eligible else 'low',confidence_reason='Проверяемые поля источника; сила сигнала отделена от надёжности источника',
      content_hash=digest(title+' '+excerpt),duplicate_group_id=None,limitations=limitations,signal_subtype=subtype,
      regional_eligible=bool(eligible and customer_region and selected),country=country,federal_district=raw.get('federal_district'),
      customer_region=customer_region,customer_city=customer_city,execution_geography=raw.get('execution_geography'),
      target_market_geography=raw.get('target_market_geography'),contractor_search_geography=raw.get('contractor_search_geography'),
      remote_delivery=raw.get('remote_delivery'),organization_size=raw.get('organization_size'),geography_details=raw.get('geography_details'),
      federal_eligible=bool(eligible),event_id=raw.get('event_id'),requirements=redact(raw['requirements'])[:280] if raw.get('requirements') else None,
      dictionary_version=DICTIONARY['version'],budget_min=raw.get('budget_min'),budget_max=raw.get('budget_max'))
    return item.validate()

def deduplicate(items):
    unique=[];events={};hashes={};urls={};duplicates=0
    for item in items:
        previous=(events.get(item.event_id) if item.event_id else None) or urls.get(item.canonical_url) or hashes.get(item.content_hash)
        if previous:item.duplicate_group_id=previous.observation_id;duplicates+=1
        else:
            unique.append(item);hashes[item.content_hash]=item;urls[item.canonical_url]=item
            if item.event_id:events[item.event_id]=item
    return unique,duplicates
