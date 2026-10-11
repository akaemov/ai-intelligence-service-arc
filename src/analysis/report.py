from collections import Counter,defaultdict
from urllib.parse import urlsplit

def analyze(items,config,coverage,duplicates,previous=None):
    eligible=[o for o in items if o.regional_eligible]
    direct=[o for o in eligible if o.signal_type=='A' and o.customer_segment=='business']
    categories={}
    opportunities=[]
    for service in config['services']:
        found=[o for o in eligible if o.service_category==service]
        demands=[o for o in direct if o.service_category==service]
        categories[service]={'signals':dict(Counter(o.signal_type for o in found)), 'evidence_ids':[o.observation_id for o in found],
           'direct_b2b_events':len(demands) if any(s['status']=='ok' and s['category']=='procurement' for s in coverage) else None,
           'unit':'уникальные наблюдения в обследованных источниках, не покупатели',
           'calculation':'Дедупликация canonical URL/hash; регион + дата + категория + тип сигнала; сегменты раздельно'}
        if demands:
            domains={urlsplit(o.canonical_url).hostname for o in demands}
            opportunities.append({'service':service,'statement':'Наблюдаемые запросы требуют проверки возможности предложения услуги',
              'evidence_ids':[o.observation_id for o in demands],'confidence':'medium' if len(domains)>1 else 'low',
              'basis':f'{len(domains)} независимых доменов; отдельный случай при одном домене',
              'hypothesis':'Проверить актуальность потребности и условия закупки; не контактировать автоматически',
              'limitations':'Наблюдения не измеряют объём рынка'})
    by_city=Counter(o.city_or_district for o in eligible if o.city_or_district)
    successful=sum(s['status']=='ok' for s in coverage)
    prev_ids={o['observation_id']:o.get('content_hash') for o in (previous or {}).get('observations',[])}
    current_ids={o.observation_id:o.content_hash for o in items}
    comparable=bool(previous and previous['run']['config']==config and
        [(s['id'],s['status'],s.get('method')) for s in previous['coverage']]==[(s['id'],s['status'],s.get('method')) for s in coverage])
    return {'categories':categories,'direct_b2b_events':len(direct) if any(s['status']=='ok' and s['category']=='procurement' for s in coverage) else None,
     'audience':dict(Counter(o.customer_segment or 'unknown' for o in eligible)),
     'geography':[{'city':c,'observations':by_city.get(c) or None,'unit':'уникальные наблюдения','limitation':'Нет данных не означает отсутствие спроса'} for c in config['cities']],
     'unique_observations':len(items),'duplicates_removed':duplicates,'verified_sources':successful,
     'opportunities':opportunities,
     'swot':{'object':'Выход поставщика услуг на рынок Башкортостана','strengths':None,'weaknesses':None,
       'opportunities':opportunities,'threats':[],'limitation':'Сведения о конкретном поставщике отсутствуют; внешние угрозы не установлены'},
     'comparison':{'comparable':comparable,'new':len(current_ids.keys()-prev_ids.keys()),
       'changed':sum(prev_ids[k]!=v for k,v in current_ids.items() if k in prev_ids),
       'reason':'Дельта сохранённых наблюдений; тренд не рассчитывается: требуются завершённые сопоставимые окна и стабильное покрытие',
       'requested_compare_days':config['compare_days']},
     'limitations':['Обследованы только перечисленные источники, не весь рынок',
       'Поисковая частотность не подключена; покупателей и денежный объём рынка не оцениваем',
       'Бюджеты и цены не извлечены — нет данных; зарплаты вакансий не бюджеты услуг',
       'LLM-интерпретация и перевод отключены; факты и подсчёты выполняются программно',
       'Автоматический анализ требований, отраслей, отзывов и опросов не подключён',
       'Период RSS ограничен доступной лентой, HH — последними 30 днями',
       'Неполное покрытие: спрос неизвестен' if successful<len(coverage) else 'Даже полное покрытие настроенных источников не описывает весь рынок']}
