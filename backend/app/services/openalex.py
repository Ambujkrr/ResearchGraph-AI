import asyncio
import re
from datetime import date
from urllib.parse import unquote
import httpx

class OpenAlexError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status

def normalize_id(value: str) -> str:
    if not isinstance(value, str): raise ValueError('Invalid OpenAlex work ID')
    match = re.fullmatch(r'(?:https?://openalex\.org/)?(W[0-9]+)', value.strip(), re.I)
    if not match: raise ValueError('Invalid OpenAlex work ID')
    return 'https://openalex.org/' + match.group(1).upper()

def normalize_doi(value: str | None) -> str | None:
    if not value or not isinstance(value, str): return None
    result = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value.strip(), flags=re.I)
    result = unquote(result).strip().lower()
    return result if re.fullmatch(r'10\.\d{4,9}/\S+', result) and len(result) <= 512 else None

def abstract_from_index(index):
    if index is None: return None
    if not isinstance(index, dict): return None
    if not index: return ''
    positions = {}
    for word, indexes in index.items():
        if not isinstance(word,str) or not isinstance(indexes,list): return None
        for i in indexes:
            if type(i) is not int or i < 0 or i > 100000 or i in positions: return None
            positions[i] = word
    if not positions: return ''
    if set(positions) != set(range(len(positions))): return None
    return ' '.join(positions[i] for i in range(len(positions)))

def parse_work(work):
    if not isinstance(work,dict): raise ValueError('Invalid work')
    ident=normalize_id(work.get('id',''))
    title=work.get('title')
    if not isinstance(title,str) or not title.strip(): raise ValueError('Missing title')
    try: published=date.fromisoformat(work['publication_date']) if work.get('publication_date') else None
    except (ValueError,TypeError): published=None
    year=work.get('publication_year'); year=year if type(year) is int and 1000 <= year <= 3000 else None
    count=work.get('cited_by_count'); count=count if type(count) is int and count>=0 else None
    authors=[]
    authorships=work.get('authorships'); authorships=authorships if isinstance(authorships,list) else []
    for item in authorships:
        if isinstance(item,dict) and isinstance(item.get('author'),dict):
            author=item['author']; name=author.get('display_name')
            if isinstance(name,str) and name.strip(): authors.append({'name':name, 'openalex_id':author.get('id') if isinstance(author.get('id'),str) else None})
    location=work.get('primary_location'); location=location if isinstance(location,dict) else {}
    url=location.get('landing_page_url'); url=url if isinstance(url,str) and url.startswith(('https://','http://')) else ident
    doi=normalize_doi(work.get('doi'))
    refs=work.get('referenced_works'); refs=refs if isinstance(refs,list) else []
    citations=[]
    for ref in refs:
        try: citations.append(normalize_id(ref))
        except ValueError: continue
    return dict(referenced_works=list(dict.fromkeys(citations)),openalex_id=ident,title=title.strip(),abstract=abstract_from_index(work.get('abstract_inverted_index')),publication_date=published,publication_year=year,authors=authors,citation_count=count,doi=doi,normalized_doi=doi,source_url=url)

class OpenAlexClient:
    def __init__(self, key, transport=None): self.key=key; self.transport=transport
    async def get(self, path, params=None):
        if not self.key: raise OpenAlexError('OpenAlex API key is not configured', 503)
        async with httpx.AsyncClient(base_url='https://api.openalex.org', timeout=15, transport=self.transport, headers={'Authorization': 'Bearer '+self.key}) as client:
            for attempt in range(3):
                try:
                    response=await client.get(path,params=params)
                    if response.status_code in (429,500,502,503,504) and attempt < 2:
                        retry=response.headers.get('Retry-After',''); delay=min(float(retry),10) if retry.isdigit() else 0.5 * 2**attempt
                        await asyncio.sleep(delay); continue
                    if response.is_error: raise OpenAlexError(f'OpenAlex returned HTTP {response.status_code}', 429 if response.status_code==429 else 502)
                    data=response.json()
                    if not isinstance(data,dict): raise ValueError()
                    return data
                except (httpx.TimeoutException,httpx.NetworkError):
                    if attempt==2: raise OpenAlexError('OpenAlex request failed after retries', 502)
                    await asyncio.sleep(0.5 * 2**attempt)
                except ValueError: raise OpenAlexError('OpenAlex returned malformed data',502)
    async def search(self, topic, page, per_page):
        data=await self.get('/works', {'search':topic,'page':page,'per-page':per_page})
        if not isinstance(data.get('results'),list): raise OpenAlexError('OpenAlex returned malformed results')
        results=[]
        for work in data['results']:
            try: results.append(parse_work(work))
            except (ValueError,TypeError): continue
        meta=data.get('meta') if isinstance(data.get('meta'),dict) else {}
        return {'results':results,'page':page,'per_page':per_page,'total':meta.get('count')}
    async def work(self, ident):
        return parse_work(await self.get('/works/'+normalize_id(ident).rsplit('/',1)[-1]))
