import asyncio
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db.base import Base
from app.main import app
from app.models.paper import Paper,Experiment,CandidateLink,Citation
from app.services.evidence import deduplicate,validate_claims,DeterministicProvider,retrieve
from app.services.openalex import OpenAlexError

def item(id,doi=None,methods=None):return {'openalex_id':id,'doi':doi,'title':'Example','abstract':None,'retrieval_methods':methods or []}

def test_dedup_merges_identifiers_and_provenance():
    items=deduplicate([item('W1','10.1234/X',['semantic']),item('W2','https://doi.org/10.1234/x',['external'])])
    assert len(items)==1 and items[0]['retrieval_methods']==['semantic','external']

def test_citation_validation_rejects_unknown_and_missing():
    evidence=[{'citation_id':'E1'}]
    assert validate_claims([{'citations':['E1']}],evidence)['valid']
    bad=validate_claims([{'citations':['E9']},{'citations':[]}],evidence)
    assert not bad['valid'] and len(bad['errors'])==2

def test_provider_abstains_and_preserves_missing_abstracts():
    p=lambda i,a:{'citation_id':f'E{i}','title':f'Paper {i}','publication_year':None,'abstract':a}
    result=DeterministicProvider().generate({'papers':[p(1,None),p(2,''),p(3,None)]})
    assert result['review_status']=='insufficient evidence' and not result['generative_synthesis_available']
    assert result['citation_validation']['valid'] and result['supporting_evidence']==[]
    assert DeterministicProvider().generate({'papers':[]})['hypothesis'] is None

@pytest.fixture
def database():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        db.add_all([Paper(id=1,openalex_id='https://openalex.org/W1',title='Molecular drug prediction',authors=[],abstract=None),Paper(id=2,openalex_id='https://openalex.org/W2',title='Protein binding affinity',authors=[],abstract=''),Paper(id=3,openalex_id='https://openalex.org/W3',title='Molecular binding analysis',authors=[],abstract='A study')]);db.add(Experiment(id=1,status='completed',config={}));db.flush();db.add(CandidateLink(experiment_id=1,source_id=1,target_id=2,rank=1,score=.5));db.add(Citation(citing_id=1,cited_openalex_id='https://openalex.org/W3',provenance='openalex'));db.commit();yield db
    engine.dispose()

def test_hybrid_fallback_citations_and_external_provenance(database):
    class Source:
        async def search(self,topic,page,per_page):return {'results':[{'openalex_id':'https://openalex.org/W4','title':'External result','authors':[],'abstract':None,'publication_year':2020,'source_url':'https://openalex.org/W4'}]}
    with patch('app.services.evidence.encode',side_effect=RuntimeError('unavailable')):
        data=asyncio.run(retrieve(database,1,1,2,5,True,Source()))
    assert data['papers'][0]['abstract'] is None and data['papers'][1]['abstract']==''
    paper=next(p for p in data['papers'] if p['openalex_id'].endswith('W3'))
    assert 'lexical_title' in paper['retrieval_methods'] and 'openalex_citation_reference' in paper['retrieval_methods']
    assert any(not p['local'] and p['retrieval_methods']==['openalex_external_search'] for p in data['papers'])
    assert data['warnings'] and len(data['papers'])<=5

def test_external_failure_keeps_local(database):
    class Source:
        async def search(self,*args):raise OpenAlexError('HTTP 429',429)
    with patch('app.services.evidence.encode',side_effect=RuntimeError()): data=asyncio.run(retrieve(database,1,1,2,4,True,Source()))
    assert len(data['papers'])>=2 and any('External' in w for w in data['warnings'])

def test_api_bounds_and_provider_unavailable():
    c=TestClient(app)
    assert not c.get('/api/v1/analysis/providers').json()['generative_synthesis_available']
    assert c.post('/api/v1/analyses',json={'experiment_id':1,'source_id':1,'target_id':2,'top_k':16}).status_code==422
    assert c.post('/api/v1/analyses',json={'experiment_id':1,'source_id':1,'target_id':2,'provider':'imaginary'}).status_code==503


def test_interrupted_analysis_recovery(database):
    from app.api.v1.analyses import recover
    from app.models.paper import ResearchAnalysis
    job=ResearchAnalysis(experiment_id=1,source_id=1,target_id=2,status='running',config={},provider='deterministic')
    database.add(job);database.commit();recover(database);database.refresh(job)
    assert job.status=='interrupted' and 'stopped' in job.error


def test_doi_resolver_check_is_bounded_and_never_follows_redirect(database,monkeypatch):
    from app.api.v1.analyses import verify_citation
    from app.models.paper import ResearchAnalysis
    job=ResearchAnalysis(id=1,experiment_id=1,source_id=1,target_id=2,status='completed',config={},provider='deterministic',evidence={'papers':[{'citation_id':'E1','doi':'10.1234/example'}]})
    database.add(job);database.commit();seen={}
    class Response:status_code=302
    class Client:
        def __init__(self,**kwargs):seen.update(kwargs)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def head(self,url):seen['url']=url;return Response()
    monkeypatch.setattr('app.api.v1.analyses.httpx.AsyncClient',Client)
    result=asyncio.run(verify_citation(1,'E1',database))
    assert result['status']=='resolver_responded' and seen['follow_redirects'] is False and seen['url'].startswith('https://doi.org/')


def test_provider_failure_persists_deterministic_fallback(database,monkeypatch):
    from app.api.v1 import analyses
    from app.models.paper import ResearchAnalysis
    from app.services.gemini import ProviderUnavailable
    from sqlalchemy.orm import sessionmaker
    job=ResearchAnalysis(id=2,experiment_id=1,source_id=1,target_id=2,status='running',config={'provider':'mock'},provider='mock');database.add(job);database.commit()
    factory=sessionmaker(bind=database.bind,expire_on_commit=False)
    p=lambda i:{'citation_id':f'E{i}','title':f'Paper {i}','publication_year':2020,'abstract':None}
    monkeypatch.setattr(analyses,'SessionLocal',factory);monkeypatch.setattr(analyses,'retrieve_sync',lambda cfg:{'papers':[p(1),p(2)]})
    class Broken:
        def generate(self,e):raise ProviderUnavailable('Unavailable for test')
    monkeypatch.setattr(analyses,'get_provider',lambda name:Broken());monkeypatch.setattr(analyses,'release_owner',lambda owner:None)
    analyses.execute(2,None);database.expire_all();saved=database.get(ResearchAnalysis,2)
    assert saved.status=='completed' and not saved.synthesis['generative_synthesis_available'] and 'Unavailable for test' in saved.synthesis['fallback_reason']


def test_gemini_daily_cap_counts_attempts_and_falls_back(database,monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy import select,func
    from sqlalchemy.orm import sessionmaker
    from app.api.v1 import analyses
    from app.models.paper import ResearchAnalysis,GenerationAttempt
    factory=sessionmaker(bind=database.bind,expire_on_commit=False)
    for i in (10,11,12):database.add(ResearchAnalysis(id=i,experiment_id=1,source_id=1,target_id=2,status='running',config={'provider':'gemini'},provider='gemini'))
    database.commit();p=lambda i:{'citation_id':f'E{i}','title':f'Paper {i}','publication_year':2020,'abstract':None}
    monkeypatch.setattr(analyses,'SessionLocal',factory);monkeypatch.setattr(analyses,'retrieve_sync',lambda cfg:{'papers':[p(1),p(2)]});monkeypatch.setattr(analyses,'release_owner',lambda owner:None)
    monkeypatch.setattr(analyses,'get_settings',lambda:SimpleNamespace(gemini_api_key='fake',gemini_free_tier_confirmed=True,gemini_daily_request_limit=2))
    calls=[]
    class Provider:
        def generate(self,e):calls.append(1);return {'provider':'gemini','generative_synthesis_available':True}
    monkeypatch.setattr(analyses,'get_provider',lambda name:Provider())
    for i in (10,11,12):analyses.execute(i,None)
    database.expire_all();assert len(calls)==2 and database.scalar(select(func.count()).select_from(GenerationAttempt))==2
    assert 'daily request limit' in database.get(ResearchAnalysis,12).synthesis['fallback_reason']
