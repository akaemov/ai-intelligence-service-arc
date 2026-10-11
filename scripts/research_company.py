"""Read permitted company pages; publish only bounded, redacted factual extracts."""
import argparse,json,re,time,sys,urllib.request,urllib.error,urllib.robotparser
from collections import deque
from urllib.parse import urljoin,urlsplit,urlunsplit
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.collectors.dom import DOM
from src.models import redact
AGENT='PublicCompanyResearch/1.0 (+https://github.com/akaemov/ai-intelligence-service-arc)'
def compact(value):return ' '.join(value.split())
def emit(value):
    payload=json.dumps(value,ensure_ascii=False)
    pieces=[payload[i:i+1800] for i in range(0,len(payload),1800)]
    for index,piece in enumerate(pieces):
        data=json.dumps({'url':value.get('url'),'part':index,'parts':len(pieces),'data':piece},ensure_ascii=False)
        print('::notice title=Company research::'+data.replace('%','%25').replace('\r','%0D').replace('\n','%0A'),flush=True)
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
        if requests>=70 or time.monotonic()-started>240:raise RuntimeError('Collection limit')
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
            headings=[redact(compact(n.text()))[:150] for n in tree.nodes() if n.tag in ('h1','h2','h3','h4')]
            descriptions=[redact(n.attrs.get('content',''))[:350] for n in tree.nodes('meta') if (n.attrs.get('name') or n.attrs.get('property')) in ('description','og:description')]
            points=[]
            for n in tree.nodes():
                text=compact(n.text())
                if n.tag in ('p','li') and 15<len(text)<450 and (n.tag=='li' or re.search(r'компан|услуг|проект|клиент|лет|город|адрес|производ|работ|предлага|разработ|партнер|партнёр|₽|руб|Москва|Уфа|Башк',text,re.I)):
                    point=redact(text)[:180]
                    if point not in points:points.append(point)
            emit({'url':url,'status':'ok','title':[n.text()[:200] for n in tree.nodes('title')][:1],
                'descriptions':list(dict.fromkeys(descriptions)),'headings':list(dict.fromkeys(headings))[:30],
                'points':points[:18],'excerpt':redact(compact(tree.text()))[:280],
                'links':links[:55] if completed==1 else links[:20]})
        except Exception as e:emit({'url':url,'status':'error','error':type(e).__name__+(' HTTP '+str(e.code) if hasattr(e,'code') else '')})
    emit({'url':base,'status':'coverage','pages':completed,'requests':requests,'remaining_urls':list(queue)[:50],'limits':{'max_pages':max_pages,'max_requests':70,'max_seconds':240}})
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);parser.add_argument('--max-pages',type=int,default=20);args=parser.parse_args()
    if not 1<=args.max_pages<=30:raise ValueError('Invalid page count')
    research(args.url,args.max_pages)
