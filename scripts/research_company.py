"""Read permitted company pages; publish only bounded, redacted factual extracts."""
import argparse,json,re,time,sys,urllib.request,urllib.error,urllib.robotparser,gzip,base64
from collections import deque
from urllib.parse import urljoin,urlsplit,urlunsplit
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.collectors.dom import DOM
from src.models import redact
AGENT='PublicCompanyResearch/1.0 (+https://github.com/akaemov/ai-intelligence-service-arc)'
def compact(value):return ' '.join(value.split())
RECORDS=[]
def notice(value):
    payload=base64.b64encode(gzip.compress(json.dumps(value,ensure_ascii=False).encode())).decode()
    pieces=[payload[i:i+1800] for i in range(0,len(payload),1800)]
    for index,piece in enumerate(pieces):
        data=json.dumps({'encoding':'gzip-base64','record_key':str(value.get('url'))+'::'+str(value.get('status')),'url':value.get('url'),'part':index,'parts':len(pieces),'data':piece},ensure_ascii=False)
        print('::notice title=Company research::'+data.replace('%','%25').replace('\r','%0D').replace('\n','%0A'),flush=True)
def emit(value):RECORDS.append(value)
def research(base,max_pages):
    host=urlsplit(base).hostname
    if not host or urlsplit(base).scheme!='https':raise ValueError('HTTPS homepage required')
    hosts={host,host.removeprefix('www.'),'www.'+host.removeprefix('www.')}
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            if urlsplit(newurl).scheme!='https' or urlsplit(newurl).hostname not in hosts:raise ValueError('External redirect rejected')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    opener=urllib.request.build_opener(Redirect());robots={};started=time.monotonic();requests=0
    def get(url):
        nonlocal requests
        if requests>=110 or time.monotonic()-started>360:raise RuntimeError('Collection limit')
        if urlsplit(url).scheme!='https' or urlsplit(url).hostname not in hosts:raise ValueError('External fetch rejected')
        time.sleep(.3);requests+=1
        with opener.open(urllib.request.Request(url,headers={'User-Agent':AGENT}),timeout=12) as r:
            body=r.read(4000001)
            if len(body)>4000000:raise ValueError('Oversize page')
            return body.decode('utf-8','replace'),r.headers.get('Content-Type','')
    def allowed(url):
        u=urlsplit(url);origin=u.scheme+'://'+u.netloc
        if origin not in robots:
            rp=urllib.robotparser.RobotFileParser()
            try:body,_=get(origin+'/robots.txt');rp.parse(body.splitlines())
            except urllib.error.HTTPError as e:
                if e.code==404:rp.parse([])
                else:raise
            robots[origin]=rp
        return robots[origin].can_fetch(AGENT,url)
    queue=deque([base]);seen=set();completed=0
    while queue and completed<max_pages:
        url=queue.popleft()
        if url in seen:continue
        seen.add(url)
        try:
            if not allowed(url):emit({'url':url,'status':'robots_denied'});continue
            body,kind=get(url)
            if 'html' not in kind:continue
            tree=DOM(body).root;completed+=1
            links=[]
            for a in tree.nodes('a'):
                href=urljoin(url,a.attrs.get('href',''));u=urlsplit(href)
                if u.scheme not in ('http','https'):continue
                href=urlunsplit((u.scheme,u.netloc,u.path,u.query,''))
                if not any(x['url']==href for x in links):links.append({'url':href,'label':redact(compact(a.text()))[:100]})
                if u.scheme=='https' and u.hostname in hosts and not u.query and not re.search(r'\.(?:jpg|png|pdf|zip|svg|webp|mp4|css|js)$|/wp-|/feed/|/login|/admin',u.path,re.I):
                    if href not in seen and href not in queue:queue.append(href)
            main=next(iter(tree.nodes('main')),tree)
            def meaningful(n):
                ancestor=n
                while ancestor and ancestor.tag!='root':
                    if ancestor.tag in ('body','html'):break
                    if ancestor.tag in ('header','nav','footer','aside') or re.search(r'(?:^|[-_ ])(?:header|menu|footer|nav|modal|popup|basket|bvi|dropdown)(?:$|[-_ ])',ancestor.attrs.get('class',''),re.I):return False
                    ancestor=ancestor.parent
                return True
            headings=[redact(compact(n.text()))[:150] for n in main.nodes() if n.tag in ('h1','h2','h3','h4') and meaningful(n)]
            descriptions=[redact(n.attrs.get('content',''))[:350] for n in tree.nodes('meta') if (n.attrs.get('name') or n.attrs.get('property')) in ('description','og:description')]
            points=[]
            for n in main.nodes():
                if not meaningful(n):continue
                text=compact(n.text())
                if n.tag in ('p','li') and 15<len(text)<450 and (n.tag=='li' or re.search(r'компан|услуг|проект|клиент|лет|город|адрес|производ|работ|предлага|разработ|партнер|партнёр|₽|руб|Москва|Уфа|Башк',text,re.I)):
                    point=redact(text)[:180]
                    if point not in points:points.append(point)
            sections=[]
            for h in main.nodes():
                if h.tag not in ('h1','h2','h3','h4') or not meaningful(h) or not h.parent:continue
                siblings=h.parent.children;index=siblings.index(h);texts=[]
                for n in siblings[index+1:index+5]:
                    if isinstance(n,str):text=compact(n)
                    else:
                        if n.tag in ('h1','h2','h3','h4'):break
                        text=compact(n.text())
                    if text:texts.append(text)
                if texts:sections.append({'heading':redact(compact(h.text()))[:150],'excerpt':redact(' '.join(texts))[:280]})
            emit({'url':url,'status':'ok','title':[n.text()[:200] for n in tree.nodes('title')][:1],
                'descriptions':list(dict.fromkeys(descriptions)),'headings':list(dict.fromkeys(headings))[:30],
                'points':points[:18],'excerpt':redact(compact(main.text()))[:280],
                'metrics':list(dict.fromkeys(redact(compact(n.text()))[:150] for n in main.nodes() if meaningful(n) and n.tag in ('div','span','p') and 8<len(compact(n.text()))<150 and re.search(r'\d[^.]{0,50}(?:лет|проект|объект|сотрудник|м²|м2|дней|регион|%|руб|₽)',n.text(),re.I)))[:20],
                'section_context':sections[:15],
                'specifications':[[redact(compact(c.text()))[:120] for c in row.nodes() if c.tag in ('td','th')] for row in main.nodes('tr')][:25],
                'structure':{'main_tags':len(tree.nodes('main')),'h1_parents':[n.parent.attrs.get('class','') for n in tree.nodes('h1')][:2]},
                'links':[l for l in links if urlsplit(l['url']).hostname not in hosts and urlsplit(l['url']).hostname not in ('wa.me','api.whatsapp.com')][:15],
                'content_links':[{'url':urljoin(url,a.attrs.get('href','')),'label':redact(compact(a.text()))[:120]} for a in main.nodes('a') if meaningful(a) and compact(a.text()) and (not a.attrs.get('href','').startswith(('tel:','mailto:')) or '/contacts' in url)][:35],
                'images':[{'alt':redact(n.attrs.get('alt',''))[:100],'url':urljoin(url,n.attrs.get('src',''))} for n in main.nodes('img') if meaningful(n) and n.attrs.get('alt')][:25],
                'internal_links': [l for l in links if urlsplit(l['url']).hostname in hosts][:70] if completed==1 else []})
            def priority(u):
                path=urlsplit(u).path;depth=path.strip('/').count('/')
                if depth<=1 and re.search(r'company|contact|service|uslugi|landings|info|gallery|sitemap',path,re.I):return (0,depth)
                if depth<=1:return (1,depth)
                if re.search(r'landings|info',path,re.I):return (2,depth)
                if re.search(r'/product/',path):return (3,depth)
                if re.search(r'/projects/',path):return (4,depth)
                return (5,depth)
            queue=deque(sorted(queue,key=priority))
        except Exception as e:emit({'url':url,'status':'error','error':type(e).__name__+(' HTTP '+str(e.code) if hasattr(e,'code') else '')})
    emit({'url':base,'status':'coverage','pages':completed,'requests':requests,'remaining_urls':list(queue)[:50],'limits':{'max_pages':max_pages,'max_requests':110,'max_seconds':360}})
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url');parser.add_argument('--max-pages',type=int,default=60);parser.add_argument('--output');parser.add_argument('--input');parser.add_argument('--emit-index',type=int);args=parser.parse_args()
    if args.input:
        records=json.loads(Path(args.input).read_text())
        if args.emit_index<len(records):notice(records[args.emit_index])
    else:
        if not args.url or not 1<=args.max_pages<=60:raise ValueError('Invalid collection arguments')
        research(args.url,args.max_pages)
        if args.output:
            path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(RECORDS,ensure_ascii=False))
            notice(RECORDS[-1])
        else:
            for record in RECORDS:notice(record)
