"""Metadata drafts only: ISBN cover completion and guarded public URL previews."""
import os
import re
from html import unescape
from urllib.parse import urlsplit, quote, urljoin
import httpx
from html.parser import HTMLParser
from fastapi import HTTPException

HOSTS = {'www.googleapis.com','openlibrary.org','api.openbd.jp','api.themoviedb.org','api.crossref.org','itunes.apple.com'}


async def provider_json(url, params=None):
    if urlsplit(url).hostname not in HOSTS or not url.startswith('https://'):
        raise RuntimeError('Unsupported metadata host')
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            async with client.stream('GET',url,params=params,headers={'User-Agent':'Monoreader/8 (personal metadata lookup)','Accept':'application/json'}) as response:
                if response.status_code in (401,403):
                    raise HTTPException(502,'資料來源拒絕查詢，請檢查 API Key 或其權限限制。')
                if response.status_code == 429: raise HTTPException(503,'資料來源的查詢額度暫時用盡，請稍後重試。')
                if response.status_code == 404: return {}
                if response.status_code != 200: raise HTTPException(502,'資料來源暫時未能回應，請稍後重試。')
                content=bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content)>2000000: raise HTTPException(502,'資料來源回應過大，請改用手動填寫。')
                import json
                return json.loads(content)
    except HTTPException: raise
    except (httpx.HTTPError,ValueError,TypeError):
        # Never echo a request URL: it may contain a provider credential.
        raise HTTPException(502,'外部資料來源連線失敗或格式不符，請稍後重試。') from None


def text(value, limit=1000):
    return unescape(re.sub(r'<[^>]*>','',str(value or ''))).strip()[:limit]


def safe_url(value):
    value=str(value or '')[:4000]
    try:
        u=urlsplit(value)
        return value if u.scheme in ('http','https') and u.hostname and not u.username and not u.password else ''
    except ValueError: return ''


def isbn_clean(value):
    value=re.sub(r'^ISBN(?:-1[03])?\s*:?\s*','',value.strip(),flags=re.I)
    value=re.sub(r'[\s-]','',value.upper())
    if re.fullmatch(r'\d{9}[\dX]',value):
        if sum((10-i)*(10 if c=='X' else int(c)) for i,c in enumerate(value))%11==0:return value
    if re.fullmatch(r'97[89]\d{10}',value):
        if sum(int(c)*(1 if i%2==0 else 3) for i,c in enumerate(value))%10==0:return value
    raise HTTPException(400,'ISBN 格式或校驗碼不正確。請輸入完整的 10 或 13 位 ISBN，可包含連字號。')


def isbn13(value):
    if len(value)==13:return value
    stem='978'+value[:9]
    return stem+str((-sum(int(c)*(1 if i%2==0 else 3) for i,c in enumerate(stem)))%10)


def draft(kind, fields, provider, category='', warnings=None):
    fields={k:safe_url(v) if k in ('url','image') else text(v,50000 if k in ('summary','notes') else 1000) for k,v in fields.items()}
    if not fields.get('title'):raise HTTPException(404,'查到的資料沒有標題，請改用手動填寫。')
    return {'type':kind,'fields':fields,'provider':provider,'category':category,'warnings':warnings or []}


async def lookup_isbn_record(value):
    isbn=isbn_clean(value);canonical=isbn13(isbn);warnings=[];errors=[]
    if canonical.startswith(('9787','978957','978986','978626','978988','978962')):
        try:
            found=await lookup_douban(canonical)
            if found:return found
        except HTTPException:
            warnings.append('豆瓣未能提供可核對的書目，已改查其他來源。')
    # Japanese editions often have better local metadata in openBD.
    if canonical.startswith('9784'):
        try:
            data=await provider_json('https://api.openbd.jp/v1/get',{'isbn':isbn})
            info=data[0].get('summary',{}) if isinstance(data,list) and data and isinstance(data[0],dict) else {}
            if info.get('title'):
                cover=info.get('cover')
                if not cover:warnings.append('找到日文書目，但未取得封面；可手動填寫圖片網址。')
                return draft('book',{'title':info['title'],'author':info.get('author'),'source':info.get('publisher'),'published':info.get('pubdate'),'identifier':isbn,'image':cover,'url':f'https://www.hanmoto.com/bd/isbn/{canonical}'},'openBD',warnings=warnings)
        except HTTPException as exc:errors.append(exc)
    if canonical.startswith(('9784','9794')):
        try:
            found=await lookup_ndl(canonical)
            if found:return found
        except HTTPException:pass
    params={'q':'isbn:'+isbn,'maxResults':5,'printType':'books'}
    if os.getenv('GOOGLE_BOOKS_API_KEY'):params['key']=os.environ['GOOGLE_BOOKS_API_KEY'].strip()
    try:
        data=await provider_json('https://www.googleapis.com/books/v1/volumes',params)
        for item in data.get('items',[]):
            info=item.get('volumeInfo',{});ids=[]
            for entry in info.get('industryIdentifiers',[]):
                try: ids.append(isbn13(isbn_clean(str(entry.get('identifier','')))))
                except HTTPException:pass
            if canonical not in ids:continue
            cover=info.get('imageLinks',{}).get('thumbnail','').replace('http://','https://',1)
            return draft('book',{'title':info.get('title'),'author':', '.join(info.get('authors',[])),'source':info.get('publisher'),'published':info.get('publishedDate'),'identifier':isbn,'summary':info.get('description'),'image':cover,'url':info.get('infoLink')},'Google Books',warnings=warnings)
    except HTTPException as exc:
        errors.append(exc);warnings.append('Google Books 未能回應，已改用備援來源。')
    try:
        data=await provider_json('https://openlibrary.org/api/books',{'bibkeys':'ISBN:'+isbn,'format':'json','jscmd':'data'})
        info=data.get('ISBN:'+isbn,{})
        if info.get('title'):
            return draft('book',{'title':info.get('title'),'author':', '.join(a.get('name','') for a in info.get('authors',[])),'source':', '.join(a.get('name','') for a in info.get('publishers',[])),'published':info.get('publish_date'),'identifier':isbn,'url':info.get('url') or f'https://openlibrary.org/isbn/{isbn}','image':info.get('cover',{}).get('large') or info.get('cover',{}).get('medium')},'Open Library',warnings=warnings)
    except HTTPException as exc:errors.append(exc)
    try:
        data=await provider_json('https://api.crossref.org/works',{'filter':'isbn:'+canonical,'rows':3})
        for info in data.get('message',{}).get('items',[]):
            ids=[]
            for v in info.get('ISBN',[]):
                try:ids.append(isbn13(isbn_clean(v)))
                except HTTPException:pass
            if canonical not in ids or not info.get('title'):continue
            return draft('book',{'title':info['title'][0],'author':', '.join(' '.join(filter(None,[a.get('given'),a.get('family')])) for a in info.get('author',[])),'source':info.get('publisher'),'identifier':isbn,'url':info.get('URL'),'summary':info.get('abstract')},'Crossref',warnings=warnings+['此來源未提供封面。'])
    except HTTPException as exc:errors.append(exc)
    if errors:raise HTTPException(502,'未取得此 ISBN 的書目，且部分來源查詢失敗。'+errors[0].detail+' 亦可手動新增。')
    raise HTTPException(404,'未找到符合此 ISBN 的書目；可改用手動新增，不會自動套用其他版本。')


async def lookup_imdb(value):
    if re.fullmatch(r'tt\d{7,12}',value):imdb=value
    else:
        u=urlsplit(value)
        if u.scheme not in ('http','https') or u.hostname not in ('imdb.com','www.imdb.com','m.imdb.com') or u.username or u.password:
            raise HTTPException(400,'請輸入 IMDb 作品網址或 tt 開頭的作品編號。')
        match=re.fullmatch(r'/title/(tt\d{7,12})/?',u.path)
        if not match:raise HTTPException(400,'請使用 IMDb /title/ 作品網址，不能使用人物或搜尋網址。')
        imdb=match.group(1)
    key=os.getenv('TMDB_API_KEY','').strip()
    if not key:raise HTTPException(503,'請在 Vercel 設定 TMDB_API_KEY（v3 API Key）並重新部署，才能以 IMDb 檢索。')
    params={'api_key':key,'external_source':'imdb_id','language':'zh-TW'}
    data=await provider_json('https://api.themoviedb.org/3/find/'+imdb,params)
    kind='movie' if data.get('movie_results') else 'tv'
    matches=data.get('movie_results') or data.get('tv_results') or []
    if not matches:raise HTTPException(404,'TMDB 未找到此 IMDb 電影或影集；單集及人物暫不支援，請手動填寫。')
    item=matches[0];creator='';warnings=[]
    tmdb_id=item.get('id')
    if not isinstance(tmdb_id,int):raise HTTPException(502,'TMDB 回傳的作品編號不正確。')
    try:
        detail=await provider_json(f'https://api.themoviedb.org/3/{kind}/{tmdb_id}',{'api_key':key,'language':'zh-TW','append_to_response':'credits'})
        creator=', '.join(c.get('name','') for c in detail.get('credits',{}).get('crew',[]) if c.get('job')=='Director') if kind=='movie' else ', '.join(c.get('name','') for c in detail.get('created_by',[]))
        item={**item,**detail}
    except HTTPException: warnings.append('已取得作品，但未能補齊導演／創作者資料。')
    poster=item.get('poster_path','')
    return draft('media',{'title':item.get('title') or item.get('name') or item.get('original_title') or item.get('original_name'),'author':creator,'published':item.get('release_date') or item.get('first_air_date'),'summary':item.get('overview'),'url':f'https://www.imdb.com/title/{imdb}/','image':'https://image.tmdb.org/t/p/w500'+poster if poster and poster.startswith('/') else ''},'TMDB','電影與影集',warnings)


async def lookup_doi(value):
    doi=re.sub(r'^https?://(?:dx\.)?doi\.org/','',value,flags=re.I)
    if not re.fullmatch(r'10\.\d{4,9}/\S+',doi):raise HTTPException(400,'請輸入有效 DOI 或 doi.org 網址。')
    data=await provider_json('https://api.crossref.org/works/'+quote(doi,safe=''))
    item=data.get('message',{})
    if not isinstance(item,dict) or not item.get('title'):raise HTTPException(404,'Crossref 沒有此 DOI 的資料。')
    parts=(item.get('published',{}).get('date-parts') or [[]])[0]
    date='-'.join(str(n) if i==0 else str(n).zfill(2) for i,n in enumerate(parts))
    issue=', '.join(x for x in ['Vol. '+str(item['volume']) if item.get('volume') else '', 'Issue '+str(item['issue']) if item.get('issue') else ''] if x)
    return draft('journal',{'title':item['title'][0],'author':', '.join(' '.join(filter(None,[a.get('given'),a.get('family')])) or a.get('name','') for a in item.get('author',[])),'source':(item.get('container-title') or [item.get('publisher','')])[0],'published':date,'issue':issue,'identifier':doi,'summary':item.get('abstract'),'url':'https://doi.org/'+doi},'Crossref')


async def lookup_apple(value):
    u=urlsplit(value)
    if u.scheme not in ('http','https') or u.hostname != 'music.apple.com' or u.username or u.password:
        raise HTTPException(400,'請輸入 music.apple.com 的專輯網址。')
    match=re.fullmatch(r'/([a-zA-Z]{2})/album/(?:[^/]+/)?(\d+)/?',u.path)
    if not match:raise HTTPException(400,'請輸入 Apple Music 專輯網址；播放清單暫不支援。')
    data=await provider_json('https://itunes.apple.com/lookup',{'id':match.group(2),'country':match.group(1).lower(),'entity':'album'})
    albums=[x for x in data.get('results',[]) if str(x.get('collectionId',''))==match.group(2) and x.get('wrapperType')=='collection']
    if not albums:raise HTTPException(404,'此地區未找到專輯資訊，請改用手動新增。')
    item=albums[0]
    return draft('media',{'title':item.get('collectionName'),'author':item.get('artistName'),'published':str(item.get('releaseDate',''))[:10],'url':item.get('collectionViewUrl') or value,'image':str(item.get('artworkUrl100','')).replace('100x100bb','600x600bb'),'summary':item.get('primaryGenreName')},'Apple iTunes','音樂與專輯')


async def lookup_metadata(kind,value):
    if not isinstance(value,str) or not value.strip() or len(value)>1000:raise HTTPException(400,'請輸入 ISBN、DOI 或作品網址（最多1000字元）。')
    routes={'isbn':lookup_isbn,'imdb':lookup_imdb,'doi':lookup_doi,'apple':lookup_apple,'url':lookup_article}
    if not isinstance(kind,str) or kind not in routes:raise HTTPException(400,'不支援的檢索方式。')
    try:return await routes[kind](value.strip())
    except HTTPException:raise
    except (TypeError,ValueError,KeyError,AttributeError,IndexError):
        raise HTTPException(502,'外部資料格式不完整，請改用手動填寫。') from None


async def japanese_cover(isbn):
    # Only fixed, public publisher image hosts; never fetch a user-supplied URL.
    url=f'https://www.hanmoto.com/bd/img/{isbn}.jpg'
    try:
        async with httpx.AsyncClient(timeout=5,follow_redirects=False) as client:
            async with client.stream('GET',url) as r:
                if r.status_code==200 and r.headers.get('content-type','').startswith('image/'):
                    return url
    except httpx.HTTPError:pass
    return ''

async def douban_html(isbn):
    url='https://book.douban.com/isbn/'+isbn+'/'
    try:
        async with httpx.AsyncClient(timeout=6,follow_redirects=False) as client:
            for _ in range(4):
                u=urlsplit(url)
                if u.scheme!='https' or u.hostname!='book.douban.com' or u.username or u.password or u.port not in (None,443):
                    raise HTTPException(502,'豆瓣跳轉至不支援的位址。')
                async with client.stream('GET',url,headers={'User-Agent':'Monoreader/8 personal book lookup'}) as r:
                    if r.status_code in (301,302,303,307,308):
                        url=urljoin(url,r.headers.get('location',''));continue
                    if r.status_code!=200:raise HTTPException(502,'豆瓣暫時拒絕或無法回應查詢。')
                    body=bytearray()
                    async for chunk in r.aiter_bytes():
                        body.extend(chunk)
                        if len(body)>2000000:raise HTTPException(502,'豆瓣回應過大。')
                    return body.decode('utf-8',errors='replace'),url
    except httpx.HTTPError:
        raise HTTPException(502,'豆瓣連線未成功。') from None
    raise HTTPException(502,'豆瓣跳轉次數過多。')

async def lookup_douban(isbn):
    html,url=await douban_html(isbn)
    soup=BookHTML();soup.feed(html)
    title=soup.find(property='v:itemreviewed')
    info=soup.find(id='info')
    if not title or not info:raise HTTPException(502,'豆瓣頁面需要驗證或格式不同。')
    raw=info.text()
    match=re.search(r'ISBN\s*[:：]\s*([0-9Xx -]{10,25})',raw)
    if not match or isbn13(isbn_clean(match[1].strip()))!=isbn:
        raise HTTPException(502,'豆瓣書目 ISBN 不符，未套用。')
    def field(label):
        match=re.search(label+r'\s*[:：]\s*(.*?)(?=\s+[\w\u4e00-\u9fff]+\s*[:：]|$)',raw)
        return match[1].strip() if match else ''
    mainpic=soup.find(id='mainpic');cover=mainpic.find(tag='img') if mainpic else None;intro=soup.find_class('intro')
    return draft('book',{'title':title.text(),'author':field('作者'),'source':field('出版社'),'published':field('出版年'),'identifier':isbn,'image':cover.attrs.get('src','') if cover else '', 'url':url,'summary':intro.text() if intro else ''},'豆瓣')


class BookNode:
    def __init__(self,tag='',attrs=None):
        self.tag=tag;self.attrs=dict(attrs or []);self.children=[]
    def text(self):
        return ' '.join(x.text() if isinstance(x,BookNode) else x for x in self.children).strip()
    def find(self,tag=None,**attrs):
        if (tag is None or self.tag==tag) and all(self.attrs.get(k)==v for k,v in attrs.items()):return self
        for child in self.children:
            if isinstance(child,BookNode):
                found=child.find(tag,**attrs)
                if found is not None:return found
        return None
    def find_class(self,name):
        if name in self.attrs.get('class','').split():return self
        for child in self.children:
            if isinstance(child,BookNode):
                found=child.find_class(name)
                if found is not None:return found
        return None

class BookHTML(HTMLParser,BookNode):
    def __init__(self):
        HTMLParser.__init__(self,convert_charrefs=True);BookNode.__init__(self);self.stack=[self]
    def handle_starttag(self,tag,attrs):
        node=BookNode(tag,attrs);self.stack[-1].children.append(node)
        if tag not in ('img','br','meta','link','input','hr','source','area','base','embed','param','wbr'):self.stack.append(node)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];break
    def handle_data(self,data):
        self.stack[-1].children.append(data)


async def public_target(url):
    """Resolve once and pin a public address, including for each redirect."""
    import asyncio, socket, ipaddress
    if not safe_url(url):raise HTTPException(400,'請輸入公開的 http／https 網址。')
    u=urlsplit(url)
    if u.port not in (None,80,443):raise HTTPException(400,'不支援此連線埠。')
    try:
        rows=await asyncio.get_running_loop().getaddrinfo(u.hostname,u.port or (443 if u.scheme=='https' else 80),type=socket.SOCK_STREAM)
    except OSError:raise HTTPException(502,'無法解析網站位址。') from None
    ips=list(dict.fromkeys(row[4][0] for row in rows))
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise HTTPException(400,'只可擷取公開網站，不能存取內部網路。')
    return ips[0]


async def public_bytes(url, limit=2000000):
    import asyncio
    try:
        async with asyncio.timeout(10):
            async with httpx.AsyncClient(timeout=7,follow_redirects=False,trust_env=False) as client:
                for _ in range(5):
                    ip=await public_target(url)
                    original=httpx.URL(url)
                    # Connect to the validated IP; keep the original Host and TLS SNI.
                    target=original.copy_with(host=ip)
                    async with client.stream('GET',target,headers={'Host':original.netloc.decode(),'User-Agent':'Monoreader/12 metadata preview','Accept':'*/*'},extensions={'sni_hostname':original.host}) as r:
                        if r.status_code in (301,302,303,307,308):
                            location=r.headers.get('location')
                            if not location:raise HTTPException(502,'網站跳轉缺少目的地。')
                            url=urljoin(url,location);continue
                        if r.status_code!=200:raise HTTPException(502,'網站暫時無法讀取（HTTP '+str(r.status_code)+'）。')
                        data=bytearray()
                        async for chunk in r.aiter_bytes():
                            data.extend(chunk)
                            if len(data)>limit:raise HTTPException(502,'網站回應過大，請手動輸入。')
                        return bytes(data),url,r.headers.get('content-type','')
    except (httpx.HTTPError,TimeoutError):raise HTTPException(502,'網站連線逾時或失敗，請稍後重試。') from None
    raise HTTPException(502,'網站跳轉次數過多。')


class ArticleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.meta={};self.title=[];self.in_title=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='meta':self.meta.setdefault((a.get('property') or a.get('name') or '').lower(),a.get('content',''))
        if tag=='title':self.in_title=True
    def handle_endtag(self,tag):
        if tag=='title':self.in_title=False
    def handle_data(self,value):
        if self.in_title:self.title.append(value)


def article_draft(html,url):
    p=ArticleHTML();p.feed(html);m=p.meta
    title=m.get('og:title') or m.get('twitter:title') or ''.join(p.title)
    summary=m.get('og:description') or m.get('twitter:description') or m.get('description') or ''
    image=m.get('og:image:secure_url') or m.get('og:image') or m.get('twitter:image') or ''
    return draft('article',{'title':title,'summary':summary,'image':urljoin(url,image) if image else '',
        'url':url,'source':m.get('og:site_name') or urlsplit(url).hostname},'網頁 Open Graph／HTML',
        warnings=[] if summary else ['網站沒有提供摘要，可自行填寫。'])


async def lookup_article(value):
    body,url,kind=await public_bytes(value)
    if not any(t in kind.lower() for t in ('text/html','application/xhtml+xml')):
        raise HTTPException(400,'此網址不是可解析的文章網頁。')
    # HTML charset declarations are honored when present.
    match=re.search(br'charset=["\' ]*([a-zA-Z0-9_-]+)',body[:4096])
    encoding=match[1].decode('ascii') if match else 'utf-8'
    try:html=body.decode(encoding,errors='replace')
    except LookupError:html=body.decode('utf-8',errors='replace')
    return article_draft(html,url)


async def lookup_ndl(isbn):
    from xml.etree import ElementTree as ET
    url='https://ndlsearch.ndl.go.jp/api/opensearch?'+str(httpx.QueryParams({'isbn':isbn,'cnt':5,'dpid':'iss-ndl-opac'}))
    body,_,_=await public_bytes(url)
    if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():raise HTTPException(502,'NDL 格式不支援。')
    try:root=ET.fromstring(body)
    except ET.ParseError:raise HTTPException(502,'NDL 回應格式不符。') from None
    for item in root.findall('.//item'):
        fields={}
        for e in item:
            name=e.tag.split('}')[-1];fields.setdefault(name,[]).append(''.join(e.itertext()).strip())
        ids=[]
        for v in fields.get('identifier',[]):
            try:ids.append(isbn13(isbn_clean(v.removeprefix('urn:isbn:'))))
            except HTTPException:pass
        if isbn not in ids:continue
        first=lambda k:next(iter(fields.get(k,[])),'')
        return draft('book',{'title':first('title'),'author':', '.join(fields.get('creator',[])),
            'source':first('publisher'),'published':first('date'),'identifier':isbn,'url':first('link')},'NDL Search（國立國會圖書館）')
    return None


async def cover_candidate(url):
    if not url:return ''
    try:
        body,final,kind=await public_bytes(url)
        if kind.lower().startswith(('image/jpeg','image/png','image/webp','image/gif')) and len(body)>128:return final
    except HTTPException:pass
    return ''


async def cover_from_provider(name,isbn):
    try:
        if name=='openBD':
            d=await provider_json('https://api.openbd.jp/v1/get',{'isbn':isbn})
            return d[0].get('summary',{}).get('cover','') if isinstance(d,list) and d and isinstance(d[0],dict) else ''
        if name=='Google Books':
            d=await provider_json('https://www.googleapis.com/books/v1/volumes',{'q':'isbn:'+isbn,'maxResults':5})
            for item in d.get('items',[]):
                v=item.get('volumeInfo',{});ids=[]
                for e in v.get('industryIdentifiers',[]):
                    try:ids.append(isbn13(isbn_clean(e.get('identifier',''))))
                    except HTTPException:pass
                if isbn in ids:return v.get('imageLinks',{}).get('thumbnail','').replace('http://','https://',1)
        if name=='Open Library':
            return 'https://covers.openlibrary.org/b/isbn/'+isbn+'-L.jpg?default=false'
    except (HTTPException,TypeError,KeyError,AttributeError):pass
    return ''


async def complete_cover(isbn):
    import asyncio
    async def candidate(name,url=''):
        url=url or await cover_from_provider(name,isbn)
        return await cover_candidate(url),name
    tasks=[]
    if isbn.startswith(('9784','9794')):
        tasks.extend([asyncio.create_task(candidate('NDL Search',f'https://ndlsearch.ndl.go.jp/thumbnail/{isbn}.jpg')),
                      asyncio.create_task(candidate('版元ドットコム',f'https://www.hanmoto.com/bd/img/{isbn}.jpg')),
                      asyncio.create_task(candidate('openBD'))])
    tasks.extend(asyncio.create_task(candidate(n)) for n in ('Google Books','Open Library'))
    try:
        async with asyncio.timeout(10):
            for done in asyncio.as_completed(tasks):
                url,name=await done
                if url:return url,name
    except TimeoutError:pass
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
    return '',''


async def lookup_isbn(value):
    isbn=isbn13(isbn_clean(value))
    result=await lookup_isbn_record(value)
    if not result['fields'].get('image'):
        image,provider=await complete_cover(isbn)
        result['fields']['image']=image
        result['warnings']=[w for w in result['warnings'] if '封面' not in w]
        if image:result['warnings'].append('封面補全來源：'+provider+'；書目資料保持原來源。')
        else:result['warnings'].append('已取得書目，但各圖片來源仍未提供可用封面，可手動填寫圖片網址。')
    return result


async def lookup_cover(kind,value):
    """Image-only lookup; never replace title, summary or user notes."""
    if kind=='isbn':
        isbn=isbn13(isbn_clean(value))
        image,provider=await complete_cover(isbn)
        if not image:
            try:
                result=await lookup_isbn_record(value)
                image=result['fields'].get('image','');provider=result['provider']
            except HTTPException:pass
    elif kind in ('imdb','apple'):
        if kind=='apple' and re.fullmatch(r'\d+',value):value='https://music.apple.com/hk/album/'+value
        result=await lookup_metadata(kind,value)
        image=result['fields'].get('image','');provider=result['provider']
    else:raise HTTPException(400,'圖片搜尋僅支援 ISBN、IMDb 或 Apple Music。')
    image=safe_url(image)
    if not image:raise HTTPException(404,'未找到圖片；原資料及圖片保持不變。')
    return {'image':image,'provider':provider}
