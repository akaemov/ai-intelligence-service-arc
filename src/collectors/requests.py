"""Adapters for publicly displayed requests. No protected index/profile scraping."""
import re
from datetime import datetime,timezone
from urllib.parse import urljoin,urlsplit
from src.collectors.dom import DOM,Node
from src.collectors.adapters import iso

JOB=re.compile(r'/freelance/[^/]+/[^/]+-(\d+)/?$')
TENDER=re.compile(r'/tenders/[^/]+-(\d+)/?$')

def compact(text):return ' '.join(text.split())
def card_parent(anchor,pattern):
    node=anchor.parent;best=node
    for _ in range(5):
        if not node or node.tag in ('body','html','root'):break
        links={a.attrs.get('href') for a in node.nodes('a') if pattern.search(urlsplit(a.attrs.get('href','')).path)}
        if len(links)>1 or len(node.text())>2500:break
        best=node;node=node.parent
    return best

def records_from_html(body,url,source,config,pattern):
    tree=DOM(body).root;records=[];seen=set();directory=config.get('_directory')
    for a in tree.nodes('a'):
        href=urljoin(url,a.attrs.get('href',''));match=pattern.search(urlsplit(href).path)
        title=compact(a.text())
        if not match or len(title)<10 or title in ('Подробнее','Открыть заказ') or href in seen:continue
        seen.add(href);card=card_parent(a,pattern);text=compact(card.text())
        heading=next((n.text() for n in a.nodes() if n.has_class('c-link__underlined')),None)
        if heading:title=compact(heading)
        date=None
        for n in card.nodes('time'):
            date=iso(n.attrs.get('datetime'))
            if date:break
        if not date:
            meta=next((n.attrs.get('content') for n in card.nodes('meta') if n.attrs.get('itemprop')=='datePublished'),None)
            date=iso(meta)
        date_basis='time datetime/datePublished в карточке' if date else None
        if not date:
            # Only the isolated listing card: comments and profile dates are outside it.
            dates={n.text().strip() for n in card.nodes('span') if re.fullmatch(r'\d{2}\.\d{2}\.\d{4}',n.text().strip()) and n.parent and n.parent.has_class('whitespace-nowrap')}
            if len(dates)==1:
                date=datetime.strptime(dates.pop(),'%d.%m.%Y').replace(tzinfo=timezone.utc).isoformat()
                date_basis='Единственная явно показанная дата в изолированной карточке задания'
        location_match=re.search(r'(?:Город заказчика|Местоположение заказчика|Заказчик находится|Регион заказчика)\s*:?\s*([А-Яа-яЁё .-]{2,70})',text)
        location=location_match[1].strip() if location_match else None
        resolved=directory.resolve(location) if directory and location else None
        region,city=resolved if resolved else (None,None)
        budget=re.search(r'Бюджет\s*:?\s*([\d\s\u00a0]+)\s*(₽|руб\.?|RUB|USD|\$)',text,re.I)
        amount=float(re.sub(r'\s','',budget[1])) if budget and re.sub(r'\s','',budget[1]).isdigit() else None
        # A single unlabelled price, a salary or an agency's price is never a customer budget.
        legal=re.search(r'(?:ООО|АО|ПАО)\s+[«"][^»"]{2,100}[»"]',text)
        records.append({'title':title[:400],'url':href,'published_at':date,'request_verified':True,
          'event_id':source['id']+':'+match[1],
          'country':'Россия' if resolved else None,'customer_region':region,'customer_city':city,
          'geography_evidence':location_match[0] if resolved else None,
          'geography_details':{'customer_location':location_match[0]} if resolved else None,
          'customer_segment':'business' if legal else None,'organization_name':legal[0] if legal else None,
          'explicit_budget':amount,'currency':('RUB' if budget[2].lower() in ('₽','руб','руб.','rub') else 'USD') if amount is not None else None,
          'budget_basis':budget[0] if amount is not None else None,'price_type':'customer_budget' if amount is not None else None,
          'procurement_status':None,'remote_delivery':True if re.search(r'Возможна удаленная работа|Возможно дистанционное выполнение',text,re.I) else None,
          'date_basis':date_basis})
    return records

def workspace(client,source,config):
    # robots.txt disallows the /tenders/ index; read only permitted homepage links.
    client.allowed(source['url']);body=client.get(source['url'],page=True).decode('utf-8','replace')
    records=records_from_html(body,source['url'],source,config,TENDER)
    if not records:raise ValueError('No verified tender links on permitted homepage')
    tree=DOM(body).root
    anchors={urljoin(source['url'],a.attrs.get('href','')):a for a in tree.nodes('a') if TENDER.search(urlsplit(a.attrs.get('href','')).path)}
    for r in records:
        r['source_page']=source['url']
        a=anchors.get(r['url'])
        price=next((n for n in a.nodes('button') if any(c.has_class('rub') for c in n.nodes('span'))),None) if a else None
        if price:
            visible=compact(' '.join(c for c in price.children if isinstance(c,str)))
            match=re.fullmatch(r'(\d[\d \u00a0]*)\s*[—–]\s*(\d[\d \u00a0]*)',visible)
            lower=re.fullmatch(r'от\s*(\d[\d \u00a0]*)',visible,re.I)
            if match or lower:
                r['budget_min']=float(re.sub(r'\s','',(match or lower)[1]))
                r['budget_max']=float(re.sub(r'\s','',match[2])) if match else None
                r.update(currency='RUB',price_type='customer_budget',budget_basis=visible+'; обозначение валюты: .rub в карточке')
        if 'Идет прием заявок' in compact(a.text()) if a else False:r['procurement_status']='active'

    return records,{'method':'Только публичные ссылки на задания с разрешённой главной; запрещённый индекс /tenders/ не читается',
      'scope':'федеральная площадка, география каждого заказчика проверяется отдельно','restriction_verified':'robots.txt запрещает индекс тендеров',
      'limitations':'Дата/бюджет/география часто не представлены на главной; неизвестные не попадают в показатели','queried_regions':[]}

def weblancer(client,source,config):
    client.allowed(source['url']);home=client.get(source['url'],page=True).decode('utf-8','replace')
    tree=DOM(home).root;urls=[]
    words=('reklam','marketing','prodvizhen','smm','seo','issledovan','iskusstven','neyro','chat','bot','integratsiya-api')
    for a in tree.nodes('a'):
        href=urljoin(source['url'],a.attrs.get('href',''));path=urlsplit(href).path
        if urlsplit(href).hostname==urlsplit(source['url']).hostname and path.startswith('/freelance/') and any(w in path for w in words):
            if href not in urls and not JOB.search(path):urls.append(href)
    records=records_from_html(home,source['url'],source,config,JOB);queried=[]
    for url in urls[:max(0,config['per_source_pages']-1)]:
        try:
            client.allowed(url);body=client.get(url,page=True).decode('utf-8','replace')
            records.extend(records_from_html(body,url,source,config,JOB));queried.append(url)
        except PermissionError:continue
        except Exception:
            if records:return records,{'method':'Публичные задания и обнаруженные категории; профили и закрытые задания не читаются','scope':'география не предполагается по языку','partial':True,'queried_regions':[],'category_pages':queried}
            raise
    if not records and not queried:raise ValueError('No task pages discovered; not a successful zero-demand search')
    return records,{'method':'Публичные задания и категории, обнаруженные на главной; даты только из явной разметки','scope':'международная площадка; российские показатели только с подтверждённой географией','queried_regions':[],'category_pages':queried}
