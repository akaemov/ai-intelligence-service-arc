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
    return records, {'verified_feed_url':url,'method':'RSS: не более 150 текущих элементов; архив не обследован'}

def find_area(nodes,name):
    for node in nodes:
        if node['name'].casefold()==name.casefold():return node
        found=find_area(node.get('areas',[]),name)
        if found:return found
    return None

def hh(client,source,config):
    areas=json.loads(client.get('https://api.hh.ru/areas'))
    area=find_area(areas,config['region'])
    if not area:raise ValueError('Region not found in current HH directory')
    records=[]
    terms=[QUERIES[k][0] for k in config['services']]
    for term in terms:
        params={'area':area['id'],'text':term,'search_field':'name','period':min(config['days'],30),'per_page':50,'page':0}
        data=json.loads(client.get('https://api.hh.ru/vacancies?'+urlencode(params),page=True))
        for v in data.get('items',[]):
            records.append({'title':v['name'],'url':v['alternate_url'],'published_at':iso(v.get('published_at')),
              'verified_region':config['region'],'city':v.get('area',{}).get('name'),
              'geography_evidence':f"Региональный фильтр HH: {area['name']} (ID из /areas); место вакансии: {v.get('area',{}).get('name','неизвестно')}"})
    return records,{'method':'Одна страница на направление, до 50 вакансий; регион из /areas; период до 30 дней','actual_days':min(config['days'],30),'area_id':area['id']}

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
            region_match=re.search(r'(?:место оказания услуг|место поставки|адрес заказчика|место выполнения работ|регион заказчика)\s*:?\s*[^;]{0,220}башкортостан[^;]{0,100}',text,re.I)
            date=re.search(r'(?:размещено|дата размещения)\s*:?\s*(\d{2}\.\d{2}\.\d{4})',text,re.I)
            published=datetime.strptime(date[1],'%d.%m.%Y').replace(tzinfo=timezone.utc).isoformat() if date else None
            active=bool(re.search(r'подача заявок',text,re.I))
            # Retain only a short object-of-procurement excerpt; no customer contacts.
            obj=re.search(r'Объект закупки\s*(.*?)(?:Заказчик|Начальная|Размещено|$)',text,re.I)
            title=(obj[1].strip() if obj else '')[:280]
            if not title:continue
            records.append({'title':title,'url':link,'published_at':published,
             'procurement_status':'active' if active else 'unknown',
             'verified_region':config['region'] if region_match else None,
             'geography_evidence':'Явное указание Башкортостана в карточке ЕИС: '+text[max(0,region_match.start()-40):region_match.end()+40] if region_match else None,
             'customer_segment':'business'})
    return records,{'method':'Первая страница на направление; география и статус только из явных полей карточки','limitation':'Разметка закупок требует проверки на успешном реальном ответе'}

ADAPTERS={'hh':hh,'bashinform':rss,'rbc':rss,'eis':eis}
def collect(client,source,config):
    adapter=ADAPTERS.get(source['id'])
    if not adapter:raise ValueError('Adapter not implemented')
    return adapter(client,source) if source['category']=='media' else adapter(client,source,config)
