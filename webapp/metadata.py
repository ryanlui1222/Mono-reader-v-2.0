"""On-demand metadata drafts. No database writes, arbitrary URLs or redirects."""
import os
import re
from html import unescape
from urllib.parse import urlsplit, quote
import httpx
from fastapi import HTTPException

HOSTS = {'www.googleapis.com','openlibrary.org','api.openbd.jp','api.themoviedb.org','api.crossref.org','itunes.apple.com'}


async def provider_json(url, params=None):
    if urlsplit(url).hostname not in HOSTS or not url.startswith('https://'):
        raise RuntimeError('Unsupported metadata host')
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            async with client.stream('GET',url,params=params,headers={'User-Agent':'Monoreader/6 (personal metadata lookup)','Accept':'application/json'}) as response:
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


async def lookup_isbn(value):
    isbn=isbn_clean(value);canonical=isbn13(isbn);warnings=[];errors=[]
    # Japanese editions often have better local metadata in openBD.
    if canonical.startswith('9784'):
        try:
            data=await provider_json('https://api.openbd.jp/v1/get',{'isbn':isbn})
            info=data[0].get('summary',{}) if isinstance(data,list) and data and isinstance(data[0],dict) else {}
            if info.get('title'):
                return draft('book',{'title':info['title'],'author':info.get('author'),'source':info.get('publisher'),'published':info.get('pubdate'),'identifier':isbn,'image':info.get('cover'),'url':f'https://openlibrary.org/isbn/{isbn}'},'openBD')
        except HTTPException as exc:errors.append(exc)
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
    routes={'isbn':lookup_isbn,'imdb':lookup_imdb,'doi':lookup_doi,'apple':lookup_apple}
    if not isinstance(kind,str) or kind not in routes:raise HTTPException(400,'不支援的檢索方式。')
    try:return await routes[kind](value.strip())
    except HTTPException:raise
    except (TypeError,ValueError,KeyError,AttributeError,IndexError):
        raise HTTPException(502,'外部資料格式不完整，請改用手動填寫。') from None
