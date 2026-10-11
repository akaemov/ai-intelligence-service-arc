import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from urllib.parse import urlencode, urljoin, urlsplit

QUERIES={
 'marketing':['маркетолог','маркетинговая стратегия','лидогенерация'],
 'advertising':['реклама','таргетолог'],
 'ai':['чат-бот','искусственный интеллект','автоматизация'],
 'research':['анализ рынка','анализ конкурентов']
}

def iso(value):
    if not value: return None
    try:
        try: d=datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError: d=parsedate_to_datetime(value)
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.isoformat()
    except (ValueError,TypeError,OverflowError):return None

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.feeds=[]; self.links=[]; self.current=None; self.text=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='link' and 'rss' in a.get('type',''):self.feeds.append(a.get('href'))
        if tag=='a' and a.get('href'):self.current=a['href']; self.text=[]
    def handle_data(self,data):
        if self.current:self.text.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.current:
            self.links.append((self.current,' '.join(self.text).strip())); self.current=None

def rss(client,source):
    url=source['url']; client.allowed(url)
    body=client.get(url,page=True)
    if source['access']=='rss_discovery':
        p=Links(); p.feed(body.decode('utf-8','replace'))
        if not p.feeds:
            # Supported public-page fallback uses URLs actually discovered on this page.
            records=[]
            for href,title in p.links:
                match=re.search(r'/news/[^/]+/(\d{4}-\d{2}-\d{2})/',href)
                if match and title:
                    records.append({'title':title[:280],'url':urljoin(url,href),'published_at':iso(match[1]),'date_basis':'дата в URL издателя (точность до дня)'})
            if not records:raise ValueError('Neither RSS nor dated article links discovered')
            return records[:150],{'method':'Заголовки открытой главной; даты из URL с точностью до дня; архив не обследован','verified_page_url':url,'rss_status':'not_discovered'}
        url=urljoin(url,p.feeds[0]); client.allowed(url); body=client.get(url,page=True)
    # Feed XML is untrusted data; external entities are never resolved by ElementTree.
    tree=ET.fromstring(body)
    entries=tree.findall('.//item') or tree.findall('.//{http://www.w3.org/2005/Atom}entry')
    if not entries:raise ValueError('No RSS/Atom entries; source not verified')
    records=[]
    for item in entries[:150]:
        def value(name):
            element=item.find(name)
            if element is None:element=item.find('{http://www.w3.org/2005/Atom}'+name)
            return element.text if element is not None else None
        title=value('title'); link=value('link')
        if not link:
            element=item.find('{http://www.w3.org/2005/Atom}link')
            if element is not None:link=element.get('href')
        if not title or not link:continue
        records.append({'title':title,'url':urljoin(url,link),'published_at':iso(value('pubDate') or value('published') or value('updated'))})
    for r in records:
        if re.search(r'росси[яию]|российск',r['title'],re.I):
            r.update(country='Россия',geography_evidence='Россия явно упомянута в заголовке; только контекст, регион заказчика не установлен')
    return records, {'verified_feed_url':url,'method':'RSS: не более 150 текущих элементов; архив не обследован'}

def find_area(nodes,name):
    for node in nodes:
        if node['name'].casefold()==name.casefold():return node
        found=find_area(node.get('areas',[]),name)
        if found:return found
    return None

def hh(client,source,config):
    import os
    directory=config.get('_directory')
    if not directory:raise ValueError('Current geography directory unavailable')
    records=[];queried=[]
    areas=[(r,directory.area_id(r)) for r in config['regions']] if config['regions'] else [('Россия',directory.payload['country_provider_id'])]
    # Federal search plus balanced named areas; no guessed numeric IDs.
    if not config['regions']:
        regions=sorted(directory.regions,key=lambda r:r['name'])
        areas.extend((r['name'],r['provider_id']) for r in regions[:max(0,config['per_source_pages']-1)])
    text=' OR '.join(QUERIES[k][0] for k in config['services'])
    for name,area_id in areas[:config['per_source_pages']]:
        params={'area':area_id,'text':text,'search_field':'name','period':min(config['days'],30),'per_page':50,'page':0}
        headers={'Authorization':'Bearer '+os.environ['HH_TOKEN']} if os.environ.get('HH_TOKEN') else None
        try:data=json.loads(client.get('https://api.hh.ru/vacancies?'+urlencode(params),page=True,headers=headers))
        except Exception:
            if queried:return records,{'method':'HH API: стратифицированные региональные фильтры; первый лист до 50 вакансий, не более 30 дней','queried_regions':queried,'actual_days':min(config['days'],30),'partial':True,'error':'Одна из региональных выборок не выполнена'}
            raise
        queried.append(name)
        for v in data.get('items',[]):
            location=v.get('area',{}).get('name','');resolved=directory.resolve(location)
            region,city=resolved if resolved else (None,None)
            records.append({'title':v['name'],'url':v['alternate_url'],'published_at':iso(v.get('published_at')),
              'country':'Россия','customer_region':region,'customer_city':city,'customer_segment':'business',
              'geography_evidence':f"Место вакансии из HH: {location}; area ID {area_id} из официального /areas",
              'geography_details':{'customer_location':location,'basis':'HH vacancy area + Russia area filter'},
              'remote_delivery':None})
    return records,{'method':'HH API: федеральный и региональные фильтры; один лист до 50 вакансий, не более 30 дней','actual_days':min(config['days'],30),'queried_regions':queried,'scope':'федеральный + региональный'}

class ProcurementCards(HTMLParser):
    def __init__(self):
        super().__init__(); self.depth=0; self.parts=[]; self.links=[]; self.cards=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='div':
            if self.depth:self.depth+=1
            elif 'search-registry-entry-block' in a.get('class',''):self.depth=1;self.parts=[];self.links=[]
        if self.depth and tag=='a' and a.get('href'):self.links.append(a['href'])
    def handle_data(self,data):
        if self.depth:self.parts.append(data.strip())
    def handle_endtag(self,tag):
        if tag=='div' and self.depth:
            self.depth-=1
            if self.depth==0:self.cards.append((' '.join(x for x in self.parts if x),self.links[:]))

def eis(client,source,config):
    records=[]
    for category in config['services']:
        query={'marketing':'маркетинговые услуги','advertising':'рекламные услуги','ai':'автоматизация','research':'анализ рынка'}[category]
        url=source['url']+'?'+urlencode({'searchString':query,'pageNumber':1,'recordsPerPage':'_10'})
        client.allowed(url); html=client.get(url,page=True).decode('utf-8','replace')
        if re.search(r'captcha|капча|доступ ограничен',html,re.I):raise PermissionError('Access challenge; no bypass attempted')
        p=ProcurementCards();p.feed(html)
        if not p.cards:raise ValueError('No recognized procurement cards; parser requires verification, not a zero-demand result')
        for text,links in p.cards:
            link=next((urljoin(url,x) for x in links if 'notice' in x.lower() and 'regNumber=' in x),None)
            if not link:continue
            # Only explicit region text in the procurement card is admissible.
            location_match=re.search(r'(место оказания услуг|место поставки|адрес заказчика|место выполнения работ|регион заказчика)\s*:?\s*([^;]{1,180})',text,re.I)
            location=location_match[2] if location_match else None
            directory=config.get('_directory');resolved=None
            if directory and location:
                resolved=next(((r['name'],None) for r in directory.regions if r['name'].casefold() in location.casefold()),None)
            date=re.search(r'(?:размещено|дата размещения)\s*:?\s*(\d{2}\.\d{2}\.\d{4})',text,re.I)
            published=datetime.strptime(date[1],'%d.%m.%Y').replace(tzinfo=timezone.utc).isoformat() if date else None
            active=bool(re.search(r'подача заявок',text,re.I))
            # Retain only a short object-of-procurement excerpt; no customer contacts.
            obj=re.search(r'Объект закупки\s*(.*?)(?:Заказчик|Начальная|Размещено|$)',text,re.I)
            title=(obj[1].strip() if obj else '')[:280]
            if not title:continue
            records.append({'title':title,'url':link,'published_at':published,
             'procurement_status':'active' if active else 'unknown',
             'country':'Россия' if resolved else None,'customer_region':resolved[0] if resolved and 'заказчика' in location_match[1] else None,
             'execution_geography':location if location_match and 'заказчика' not in location_match[1] else None,
             'geography_evidence':location_match[0] if location_match else None,'request_verified':True,
             'event_id':'eis:'+next((v for k,v in __import__('urllib.parse',fromlist=['parse_qsl']).parse_qsl(urlsplit(link).query) if k=='regNumber'),link),
             'customer_segment':'government' if '44-ФЗ' in text else None})
    return records,{'method':'Первая страница на направление; география и статус только из явных полей карточки','limitation':'Разметка закупок требует проверки на успешном реальном ответе'}

ADAPTERS={'hh':hh,'bashinform':rss,'rbc':rss,'eis':eis}

def collect(client,source,config):
    if source['id'] in ('workspace','weblancer'):
        from src.collectors.requests import workspace,weblancer
        return {'workspace':workspace,'weblancer':weblancer}[source['id']](client,source,config)
    adapter=ADAPTERS.get(source['id'])
    if not adapter:raise ValueError('Adapter not implemented')
    return adapter(client,source) if source['category']=='media' else adapter(client,source,config)
