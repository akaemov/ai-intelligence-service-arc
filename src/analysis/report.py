from collections import Counter
from urllib.parse import urlsplit
from datetime import datetime
import hashlib,json

def signature(config,coverage):
    keys=('mode','regions','cities','industries','services','segments','groups','per_region_observations','per_source_pages','dictionary_version')
    value={k:config.get(k) for k in keys}
    value['sources']=[{k:s.get(k) for k in ('id','status','method','scope','queried_regions','actual_days')} for s in coverage]
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def analyze(items,config,coverage,duplicates,previous=None,directory=None):
    federal=[o for o in items if o.federal_eligible]
    direct=[o for o in federal if o.signal_type=='A']
    connected=[s for s in coverage if s['status']=='ok']
    demand_channel=any(s['category'] in ('procurement','requests') for s in connected)
    operators={s.get('operator',s['id']) for s in connected}
    minimum_ready=len(operators)>=3 and len({s['category'] for s in connected})>=2 and demand_channel and directory is not None
    categories={};opportunities=[]
    for service in config['services']:
        found=[o for o in federal if o.service_category==service]
        requests=[o for o in direct if o.service_category==service]
        b2b=[o for o in requests if o.customer_segment=='business']
        categories[service]={'signals':dict(Counter(o.signal_type for o in found)),
          'evidence_ids':[o.observation_id for o in found],'direct_b2b_events':len(b2b) if demand_channel else None,
          'direct_by_segment':dict(Counter(o.customer_segment or 'unknown' for o in requests)),
          'unit':'уникальные наблюдения, не покупатели','calculation':'Тип + период + подтверждённая Россия; регион заказчика хранится отдельно; дедупликация event_id / URL / hash'}
        if b2b:
            domains={urlsplit(o.canonical_url).hostname for o in b2b}
            opportunities.append({'service':service,'statement':'Обнаружены проверяемые запросы организаций на услугу',
              'evidence_ids':[o.observation_id for o in b2b],'confidence':'medium' if len(domains)>1 else 'low',
              'basis':f'{len(b2b)} событий; {len(domains)} доменов. Один источник не подтверждает рыночную тенденцию',
              'hypothesis':'Проверить актуальность запроса и способность исполнителя выполнить требования',
              'limitations':'Наблюдаемая выборка, не оценка российского рынка','geography':sorted({o.customer_region or 'Россия, регион неизвестен' for o in b2b}),
              'period':{'days':config['days']},'practical_value':'Основание для ручной проверки предложения; автоматические контакты не отправляются'})
    region_names=config.get('regions') or ([r['name'] for r in directory.regions] if directory else sorted({o.customer_region for o in federal if o.customer_region}))
    geography=[]
    for region in region_names:
        found=[o for o in federal if o.regional_eligible and o.customer_region==region]
        source_ids=[]
        for s in connected:
            queried=s.get('queried_regions',[])
            if region in queried or any(o.source_name==s.get('name') for o in found):source_ids.append(s['id'])
        geography.append({'region':region,'city':region,'observations':len(found) if found or source_ids else None,
          'direct_events':sum(o.signal_type=='A' for o in found) if found or source_ids else None,
          'source_ids':source_ids,'federal_district':None,'evidence_ids':[o.observation_id for o in found],
          'comparison_warning':'Покрытие регионов различается; нельзя ранжировать рынок по числу публикаций',
          'limitation':'Нет данных не означает отсутствие спроса; без знаменателя доли рынка не рассчитываются'})
    prev_obs=(previous or {}).get('observations',[])
    prev_ids={o['observation_id']:o.get('content_hash') for o in prev_obs};current_ids={o.observation_id:o.content_hash for o in items}
    sig=signature(config,coverage)
    same=bool(previous and previous['summary'].get('coverage_signature')==sig)
    # Overlapping rolling windows never yield period-over-period demand dynamics.
    comparable=False
    if same and previous['run'].get('status')=='success' and all(s['status'] in ('ok','disabled') for s in coverage):
        try:
            old_end=datetime.fromisoformat(previous['run']['period_end'])
            new_start=datetime.fromisoformat(config['_period_start'])
            comparable=old_end<=new_start and previous['run']['config']['days']==config['days']
        except (KeyError,ValueError):pass
    return {'categories':categories,'direct_b2b_events':sum(o.customer_segment=='business' for o in direct) if demand_channel else None,
      'direct_government_events':sum(o.customer_segment=='government' for o in direct) if demand_channel else None,
      'direct_unknown_events':sum(o.customer_segment is None for o in direct) if demand_channel else None,
      'audience':dict(Counter(o.customer_segment or 'unknown' for o in federal)),
      'industries':dict(Counter(o.industry or 'unknown' for o in federal)),
      'problems':[{'problem':p,'events':len(obs),'evidence_ids':[o.observation_id for o in obs],
        'limitation':'Слова в запросах, не измерение распространённости проблемы'} for p,obs in _problems(federal).items()],
      'budgets':[{'observation_id':o.observation_id,'amount':o.explicit_budget,'currency':o.currency,'price_type':o.price_type,'basis':o.budget_basis} for o in federal if o.explicit_budget is not None and o.signal_type=='A'],
      'geography':geography,'federal_without_region':sum(not o.customer_region for o in federal),
      'unknown_geography':sum(not o.federal_eligible for o in items),
      'interregional':[o.observation_id for o in direct if o.contractor_search_geography and o.contractor_search_geography!=o.customer_region],
      'unique_observations':len(items),'federal_observations':len(federal),'duplicates_removed':duplicates,
      'verified_sources':len(connected),'minimum_ready':minimum_ready,'coverage_signature':sig,'opportunities':opportunities,
      'swot':{'object':'Выход поставщика услуг на российский рынок или выбранный сегмент','strengths':None,'weaknesses':None,'opportunities':opportunities,'threats':[]},
      'comparison':{'comparable':comparable,'same_coverage':same,'new':len(current_ids.keys()-prev_ids.keys()),
        'changed':sum(prev_ids[k]!=v for k,v in current_ids.items() if k in prev_ids),
        'reason':'Техническая дельта запусков; динамика допустима только для завершённых непересекающихся периодов одинаковой длины и покрытия',
        'requested_compare_days':config['compare_days'],
        'direct_delta':len(direct)-sum(o.get('federal_eligible') and o['signal_type']=='A' for o in prev_obs) if comparable else None},
      'limitations':['Обследованные площадки не весь рынок России',
        'Нет нормализации по населению/организациям: подходящий знаменатель не подключён',
        'Москва и Санкт-Петербург ограничены теми же квотами; квоты не рыночные веса',
        'Федеральные округа неизвестны до подключения авторитетного сопоставления',
        'Перевод и поисковая частотность не подключены; опросы не считаются репрезентативными без методики',
        'Измеряются наблюдения; не уникальные покупатели и не денежный объём рынка',
        'Полный архив за 90 дней не гарантирован: фактические периоды указаны у источников',
        'Часть источников недоступна; отсутствие данных не отсутствие спроса' if len(connected)<sum(s['status']!='disabled' for s in coverage) else 'Даже успешные выбранные источники дают ограниченную выборку']}

def _problems(items):
    groups={}
    for o in items:
        if o.customer_problem:groups.setdefault(o.customer_problem,[]).append(o)
    return groups
