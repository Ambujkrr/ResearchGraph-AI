import asyncio
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.base import Base
from app.models.paper import Paper
from app.main import app
from app.api.v1.papers import client, db_session
from app.services.openalex import OpenAlexClient, OpenAlexError, abstract_from_index, normalize_doi, normalize_id, parse_work


def work(id='W1', doi='https://doi.org/10.1234/ABC'):
    return {'id':'https://openalex.org/'+id,'title':'A real-looking test fixture', 'doi':doi, 'publication_year':2020,'publication_date':'2020-01-01','cited_by_count':7,'authorships':[{'author':{'display_name':'Example Author','id':'https://openalex.org/A1'}}], 'abstract_inverted_index':{'Hello':[0,2], 'world':[1]}}

@pytest.mark.parametrize('value,expected',[(None,None),({},''),({'one':[0], 'two':[1]},'one two'),({'x':[2]},None),({'x':['bad']},None),({'x':[0], 'y':[0]},None)])
def test_abstract(value,expected): assert abstract_from_index(value)==expected

def test_parsing_and_normalization():
    paper=parse_work(work()); assert paper['abstract']=='Hello world Hello'; assert paper['authors'][0]['name']=='Example Author'; assert paper['normalized_doi']=='10.1234/abc'
    assert normalize_doi(' DOI: 10.1234/ABC ')== '10.1234/abc'
    assert normalize_id('w123')=='https://openalex.org/W123'
    broken=work(); broken.update(publication_date='no',publication_year='2020',authorships=10,cited_by_count=-2,abstract_inverted_index=[])
    p=parse_work(broken); assert p['publication_date'] is None and p['publication_year'] is None and p['authors']==[] and p['citation_count'] is None and p['abstract'] is None
    with pytest.raises(ValueError): parse_work({'id':'bad','title':'x'})

@pytest.mark.parametrize('statuses',[[429,503,200],[500,500,500]])
def test_retry_and_errors(statuses,monkeypatch):
    count=[]
    def handler(request):
        assert request.headers['Authorization']=='Bearer secret'
        assert 'secret' not in str(request.url)
        code=statuses[len(count)]; count.append(code)
        return httpx.Response(code,json={'results':[],'meta':{'count':0}})
    async def no_sleep(_): pass
    monkeypatch.setattr('app.services.openalex.asyncio.sleep',no_sleep)
    source=OpenAlexClient('secret',httpx.MockTransport(handler))
    if statuses[-1]==200: assert asyncio.run(source.search('topic',1,10))['results']==[]
    else:
        with pytest.raises(OpenAlexError): asyncio.run(source.search('topic',1,10))
    assert len(count)==3

@pytest.fixture
def api():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine); factory=sessionmaker(engine,expire_on_commit=False)
    def override_db():
        with factory() as db: yield db
    class Source:
        async def work(self,ident):
            num=ident.rsplit('/',1)[-1]
            if num=='W99': raise OpenAlexError('OpenAlex returned HTTP 503')
            return parse_work(work(num))
        async def search(self,topic,page,per_page): return {'results':[parse_work(work())], 'total':1,'page':page,'per_page':per_page}
    app.dependency_overrides[db_session]=override_db; app.dependency_overrides[client]=lambda:Source()
    with TestClient(app) as c: yield c,factory
    app.dependency_overrides.clear(); engine.dispose()

def test_ingest_idempotent_doi_and_persistence(api):
    c,factory=api
    for ident in ['W1','W1','W2']:
        assert c.post('/api/v1/papers/ingest',json={'topic':'graph','ids':[ident]}).status_code==200
    with factory() as db: assert db.scalar(select(func.count()).select_from(Paper))==1
    data=c.get('/api/v1/papers?topic=graph&year=2020&per_page=1').json(); assert data['total']==1 and len(data['results'])==1
    assert c.get('/api/v1/papers?year=2021').json()['total']==0
    assert c.get('/api/v1/papers/'+str(data['results'][0]['id'])).status_code==200
    assert c.get('/api/v1/papers?per_page=101').status_code==422

def test_ingestion_error_recorded_and_bounded(api):
    c,_=api
    response=c.post('/api/v1/papers/ingest',json={'topic':'graph','ids':['W99']})
    assert response.status_code==502
    assert c.get('/api/v1/ingestions').json()['results'][0]['status']=='failed'
    assert c.post('/api/v1/papers/ingest',json={'topic':'graph','ids':['W1']*11}).status_code==422
    assert c.get('/api/v1/openalex/search?topic=graph').json()['results'][0]['title']


def test_topics_authors_and_citations_are_deduplicated(api):
    c,factory=api
    body={'topic':'Graph Networks','ids':['W1']}
    assert c.post('/api/v1/papers/ingest',json=body).status_code==200
    body['topic']='Different Topic'
    assert c.post('/api/v1/papers/ingest',json=body).status_code==200
    assert c.get('/api/v1/papers?topic=graph%20networks').json()['total']==1
    assert c.get('/api/v1/papers?topic=different%20topic').json()['total']==1
    from app.models.paper import Author, Topic, PaperAuthor, PaperTopic
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Topic))==2
        assert db.scalar(select(func.count()).select_from(Author))==1
        assert db.scalar(select(func.count()).select_from(PaperAuthor))==1
        assert db.scalar(select(func.count()).select_from(PaperTopic))==2
    summary=c.get('/api/v1/graph/summary').json()
    assert summary['edges']['authored_by']==1 and summary['edges']['associated_with']==2
    assert c.get('/api/v1/graph/neighborhood?paper_id=1&limit=101').status_code==422
    edges=c.get('/api/v1/graph/neighborhood?paper_id=1').json()['edges']
    assert len(edges)==3 and all(e['provenance'] in ('openalex','ingestion_query') for e in edges)

def test_citations_are_only_source_backed(api):
    from app.services.graph import save_work
    from app.models.paper import Citation
    c,factory=api
    w1=parse_work(work('W1')); w2=parse_work(work('W2','10.1234/other'))
    w1['referenced_works']=['https://openalex.org/W2']
    with factory() as db:
        save_work(db,w1,'graph');save_work(db,w1,'graph');save_work(db,w2,'graph');db.commit()
        assert db.scalar(select(func.count()).select_from(Citation))==1
    result=c.get('/api/v1/graph/neighborhood?paper_id=1').json()
    assert any(e['type']=='cites' and e['provenance']=='openalex' for e in result['edges'])

def test_embedding_text_handles_missing_abstract():
    from app.services.embeddings import paper_text,content_hash
    p=Paper(title='Title',abstract=None,openalex_id='https://openalex.org/W99')
    assert paper_text(p)=='Title'
    first=content_hash(p);p.abstract='Abstract';assert content_hash(p)!=first


def test_collection_checkpoint_and_resume(api,monkeypatch):
    from app.api.v1 import collections
    c,factory=api
    calls=[]
    class Source:
        def __init__(self,*args): pass
        async def search(self,topic,page,per_page):
            calls.append(page)
            if page==2 and calls.count(2)==1: raise OpenAlexError('temporary failure')
            return {'results':[parse_work(work(f'W{page*100+i}',f'10.1234/{page}-{i}')) for i in range(25)],'page':page,'per_page':per_page,'total':100}
    monkeypatch.setattr(collections,'SessionLocal',factory)
    monkeypatch.setattr(collections,'OpenAlexClient',Source)
    response=c.post('/api/v1/collections',json={'topic':'testing','target':30})
    assert response.status_code==202
    job=c.get('/api/v1/collections').json()['results'][0]
    assert job['status']=='failed' and job['processed']==25 and job['next_page']==2
    assert c.post(f"/api/v1/collections/{job['id']}/resume").status_code==202
    job=c.get('/api/v1/collections').json()['results'][0]
    assert job['status']=='completed' and job['processed']==30 and calls==[1,2,2]
    with factory() as db: assert db.scalar(select(func.count()).select_from(Paper))==30
    assert c.post('/api/v1/collections',json={'topic':'x','target':1001}).status_code==422


def test_duplicate_author_in_one_work_is_idempotent(api):
    from app.services.graph import save_work
    from app.models.paper import PaperAuthor
    _,factory=api
    w=parse_work(work('W555'))
    w['authors'].append(w['authors'][0].copy())
    with factory() as db:
        save_work(db,w,'graph');db.commit();save_work(db,w,'graph');db.commit()
        assert db.scalar(select(func.count()).select_from(PaperAuthor))==1


def test_embedding_batches_reuse_existing_vectors(api,monkeypatch):
    from app.api.v1 import embeddings
    from app.models.paper import PaperEmbedding
    c,factory=api
    with factory() as db:
        db.add_all([Paper(openalex_id=f'https://openalex.org/W{1000+i}',title=f'Title {i}',authors=[]) for i in range(70)]);db.commit()
    sizes=[]
    def fake_encode(texts):
        sizes.append(len(texts));return [[1.0]+[0.0]*383 for _ in texts]
    monkeypatch.setattr(embeddings,'SessionLocal',factory);monkeypatch.setattr(embeddings,'encode',fake_encode)
    assert c.post('/api/v1/embeddings/generate?limit=65').status_code==202
    with factory() as db: assert db.scalar(select(func.count()).select_from(PaperEmbedding))==65
    assert max(sizes)<=16
    assert c.post('/api/v1/embeddings/generate?limit=65').status_code==202
    with factory() as db: assert db.scalar(select(func.count()).select_from(PaperEmbedding))==70
    assert sum(sizes)==70


def test_candidate_api_filters_newly_observed_citations(api):
    from app.models.paper import Experiment,CandidateLink,Citation
    c,factory=api
    with factory() as db:
        db.add_all([Paper(openalex_id='https://openalex.org/W77',title='Source',authors=[]),Paper(openalex_id='https://openalex.org/W78',title='Target',authors=[])]);db.flush()
        job=Experiment(status='completed',config={});db.add(job);db.flush()
        db.add(CandidateLink(experiment_id=job.id,source_id=1,target_id=2,rank=1,score=0.5));db.commit();job_id=job.id
    assert len(c.get(f'/api/v1/experiments/{job_id}/candidates').json()['results'])==1
    with factory() as db:db.add(Citation(citing_id=1,cited_openalex_id='https://openalex.org/W78',provenance='openalex'));db.commit()
    assert c.get(f'/api/v1/experiments/{job_id}/candidates').json()['results']==[]


def test_candidate_popularity_order_and_evidence(api):
    from app.models.paper import Experiment,CandidateLink
    c,factory=api
    with factory() as db:
        db.add_all([Paper(openalex_id=f'https://openalex.org/W{i}',title=f'Paper {i}',authors=[]) for i in (70,71,72)]);db.flush()
        job=Experiment(status='completed',config={});db.add(job);db.flush()
        db.add_all([CandidateLink(experiment_id=job.id,source_id=1,target_id=2,rank=1,score=2,popularity_rank=9,popularity_score=1,evidence={'training_common_neighbors':0}),CandidateLink(experiment_id=job.id,source_id=1,target_id=3,rank=2,score=1,popularity_rank=1,popularity_score=4,evidence={'training_common_neighbors':2})]);db.commit();job_id=job.id
    r=c.get(f'/api/v1/experiments/{job_id}/candidates?sort=popularity').json()
    assert [x['rank'] for x in r['results']]==[2,1]
    assert r['results'][0]['evidence']['training_common_neighbors']==2
    assert c.get(f'/api/v1/experiments/{job_id}/candidates?sort=bad').status_code==422
