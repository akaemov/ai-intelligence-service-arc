import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from src.models import Observation, digest, redact

LEXICON = {
 'marketing': ['маркетинг', 'маркетолог', 'лидогенерац', 'целевую аудитори', 'позиционирован', 'дорогие заявки'],
 'advertising': ['реклам', 'таргет', 'контекстн', 'продвижени'],
 'ai': ['искусственн', 'чат-бот', 'чатбот', 'ии-агент', 'внедрение ии', 'автоматиз', 'нейросет'],
 'research': ['анализ рынка', 'анализ конкурент', 'исследован', 'swot', 'собрать цены']
}
INTENT = re.compile(r'ищем (?:подрядчика|исполнителя)|нужен подрядчик|заказать |запрос коммерческ|требуется анализ рынка|ищем маркетолога|нужен чат-бот', re.I)
OFFER = re.compile(r'предлагаем|наши услуги|оказываем|наше агентство|закажите у нас', re.I)

def canonical(url):
    u = urlsplit(url)
    query = [(k,v) for k,v in parse_qsl(u.query) if not k.startswith('utm_') and k not in ('fbclid','yclid')]
    return urlunsplit((u.scheme, u.netloc.lower(), u.path or '/', urlencode(sorted(query)), ''))

def classify(title, kind):
    if kind == 'vacancies': return 'C', 'vacancy'
    if OFFER.search(title): return 'D', None
    # Procurement cards need independently verified status, intent and geography before A.
    if kind == 'media': return 'E', None
    if INTENT.search(title): return 'A', None
    if any(term in title.lower() for term in ['не приносит клиентов', 'дорогие заявки']): return 'C', None
    return 'E', None

def normalize(raw, source, run_id, config, now):
    title = re.sub(r'\s+', ' ', raw['title']).strip()
    category = next((k for k,terms in LEXICON.items() if any(t in title.lower() for t in terms)), None)
    signal, subtype = classify(title, source['category'])
    region = None
    city = None
    geo = raw.get('geography_evidence')
    if geo and raw.get('verified_region') == config['region']:
        region = config['region']; city = raw.get('city')
    # News mentioning a city or an author's address is not a regional demand proof.
    if source['category'] == 'media' and re.search('башкортостан|башкири', title, re.I):
        region = config['region']; geo = 'Территория события явно упомянута в заголовке (только контекст)'
    status = raw.get('procurement_status')
    if source['category']=='procurement' and status=='active' and region and geo and not OFFER.search(title):signal='A'
    if signal == 'A' and (not geo or not region or (source['category'] == 'procurement' and status != 'active')):
        signal = 'E'
    if not category: signal = 'F'
    published = raw.get('published_at')
    limitations = ['Автоматическая классификация; необходима ручная проверка перед коммерческим решением']
    if raw.get('date_basis'):limitations.append('Основание даты: '+raw['date_basis'])
    if 'erid=' in raw['url']:limitations.append('URL содержит рекламную маркировку erid; публикация не доказательство покупательского намерения')
    if not published: limitations.append('Дата публикации неизвестна; исключено из показателей периода')
    if not region: limitations.append('Нет подтверждённой региональной связи')
    if subtype == 'vacancy': limitations.append('Потребность в сотруднике, не заказ внешнему исполнителю; зарплата не бюджет услуги')
    if raw.get('language', 'ru') != 'ru': limitations.append('Качественный перевод не подключён; исключено из показателей')
    eligible = bool(region and geo and category in config['services'] and published and raw.get('language', 'ru') == 'ru')
    if published:
        date = datetime.fromisoformat(published)
        if date.tzinfo is None: date = date.replace(tzinfo=timezone.utc)
        age = (now - date).total_seconds() / 86400
        eligible = eligible and 0 <= age <= config['days']
        if not 0 <= age <= config['days']: limitations.append('Вне исследуемого периода')
    excerpt = redact(title)[:280]
    url = canonical(raw['url'])
    item = Observation(
        observation_id=str(uuid.uuid5(uuid.NAMESPACE_URL, url)), run_id=run_id,
        source_name=source['name'], source_type=source['category'], source_url=url, canonical_url=url,
        title=redact(title)[:400], published_at=published, collected_at=now.isoformat(), original_language=raw.get('language','ru'),
        region=region, city_or_district=city, geography_evidence=geo, organization_name=None,
        customer_segment='business' if subtype == 'vacancy' else raw.get('customer_segment'), industry=None,
        service_category=category, signal_type=signal, customer_problem=None,
        requested_service=excerpt if signal == 'A' else None,
        explicit_budget=None, currency=None, budget_basis=None, price_type=None, procurement_status=status,
        short_evidence_excerpt=excerpt, factual_summary=excerpt, analyst_interpretation=None,
        confidence_level='medium' if eligible else 'low', confidence_reason='Заголовок и метаданные источника; покупательское намерение не выводится из популярности',
        content_hash=digest(title), duplicate_group_id=None, limitations=limitations,
        signal_subtype=subtype, regional_eligible=eligible)
    return item.validate()

def deduplicate(items):
    unique=[]; hashes={}; urls={}; duplicates=0
    for item in items:
        previous = hashes.get(item.content_hash) or urls.get(item.canonical_url)
        if previous:
            item.duplicate_group_id = previous.observation_id
            duplicates += 1
        else:
            unique.append(item); hashes[item.content_hash]=item; urls[item.canonical_url]=item
    return unique, duplicates
