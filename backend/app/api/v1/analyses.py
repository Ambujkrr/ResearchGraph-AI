import asyncio, logging, threading
from datetime import datetime, timezone
from urllib.parse import quote
import httpx
from typing import Literal
from fastapi import APIRouter,BackgroundTasks,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import func,select,text,update
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app.api.v1.papers import db_session
from app.core.config import get_settings
from app.db.session import SessionLocal,engine
from app.models.paper import CandidateLink,ResearchAnalysis,GenerationAttempt
from app.services.evidence import retrieve,get_provider,DeterministicProvider
from app.services.gemini import ProviderError,ProviderUnavailable
from app.services.openalex import OpenAlexClient, normalize_doi

router=APIRouter(tags=['research analysis'])
lock=threading.Lock();retrieval_lock=threading.BoundedSemaphore(1);ADVISORY_KEY=726273151
class Request(BaseModel):
    experiment_id:int=Field(ge=1)
    source_id:int=Field(ge=1)
    target_id:int=Field(ge=1)
    top_k:int=Field(default=8,ge=2,le=15)
    include_external:bool=False
    provider:str | None=Field(default=None,max_length=40)

def acquire_owner():
    if not lock.acquire(False):return None
    connection=None
    try:
        connection=engine.connect()
        if connection.dialect.name!='postgresql':raise RuntimeError('Analysis requires PostgreSQL')
        ok=connection.scalar(text('select pg_try_advisory_lock(:key)'),{'key':ADVISORY_KEY});connection.commit()
        if not ok:connection.close();lock.release();return None
        return connection
    except Exception:
        if connection:connection.close()
        lock.release();raise

def release_owner(owner):
    try:owner.execute(text('select pg_advisory_unlock(:key)'),{'key':ADVISORY_KEY});owner.commit()
    finally:owner.close();lock.release()

def recover(db):
    db.execute(update(ResearchAnalysis).where(ResearchAnalysis.status=='running').values(status='interrupted',error='Analysis worker stopped before completion; start a new analysis.'));db.commit()

def retrieve_sync(config):
    if not retrieval_lock.acquire(blocking=False): raise RuntimeError('Evidence retrieval is busy; retry shortly')
    try:
        with SessionLocal() as db:
            return asyncio.run(retrieve(db,config['experiment_id'],config['source_id'],config['target_id'],config['top_k'],config['include_external'],OpenAlexClient(get_settings().openalex_api_key)))
    finally: retrieval_lock.release()

def execute(id,owner):
    try:
        with SessionLocal() as db:job=db.get(ResearchAnalysis,id);config=job.config
        evidence=retrieve_sync(config);requested=config['provider'];attempt_id=None
        try:
            provider=get_provider(requested)
            if requested=='gemini':
                settings=get_settings()
                if not settings.gemini_api_key or not settings.gemini_free_tier_confirmed:
                    raise ProviderUnavailable('Gemini is unavailable until an unbilled free-tier key is configured and confirmed')
                # The analysis advisory lock serializes reservation across backend workers.
                with SessionLocal() as db:
                    midnight=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
                    count=db.scalar(select(func.count()).select_from(GenerationAttempt).where(GenerationAttempt.provider=='gemini',GenerationAttempt.created_at>=midnight))
                    limit=max(0,min(settings.gemini_daily_request_limit,5))
                    if count>=limit:raise ProviderUnavailable('The local Gemini daily request limit has been reached')
                    attempt=GenerationAttempt(analysis_id=id,provider='gemini',status='reserved');db.add(attempt);db.commit();db.refresh(attempt);attempt_id=attempt.id
            synthesis=provider.generate(evidence)
            if attempt_id is not None:
                with SessionLocal() as db:attempt=db.get(GenerationAttempt,attempt_id);attempt.status='completed';db.commit()
        except ProviderError as exc:
            if attempt_id is not None:
                with SessionLocal() as db:attempt=db.get(GenerationAttempt,attempt_id);attempt.status='failed';db.commit()
            synthesis=DeterministicProvider().generate(evidence);synthesis['fallback_reason']=str(exc);synthesis['requested_provider']=requested
        with SessionLocal() as db:
            job=db.get(ResearchAnalysis,id);job.evidence=evidence;job.synthesis=synthesis;job.provider=synthesis['provider'];job.model_name=(synthesis.get('generation_metadata') or {}).get('model');job.status='completed';db.commit()
    except Exception:
        logging.getLogger(__name__).exception('Research analysis failed')
        with SessionLocal() as db:
            job=db.get(ResearchAnalysis,id)
            if job:job.status='failed';job.error='Analysis failed; inspect backend logs.';db.commit()
    finally:release_owner(owner)

@router.get('/analysis/providers')
def providers():
    default=get_settings().analysis_provider
    settings=get_settings();ready=bool(settings.gemini_api_key and settings.gemini_free_tier_confirmed and settings.gemini_model=='gemini-3.5-flash-lite')
    return {'default':default,'default_configured':default=='deterministic' or (default=='gemini' and ready),'providers':[{'name':'deterministic','configured':True,'generative':False,'model':None},{'name':'gemini','configured':ready,'generative':True,'model':settings.gemini_model,'free_tier_user_confirmed':settings.gemini_free_tier_confirmed,'daily_request_limit':max(0,min(settings.gemini_daily_request_limit,5))}],'generative_synthesis_available':ready,'note':'Free-tier status is user-confirmed, not independently verified; input may be used to improve provider products.'}

@router.get('/analysis/evidence')
async def evidence(experiment_id:int=Query(ge=1),source_id:int=Query(ge=1),target_id:int=Query(ge=1),top_k:int=Query(8,ge=2,le=15),include_external:bool=False):
    config={'experiment_id':experiment_id,'source_id':source_id,'target_id':target_id,'top_k':top_k,'include_external':include_external}
    try:return await run_in_threadpool(retrieve_sync,config)
    except ValueError as e:raise HTTPException(404,detail=str(e))
    except RuntimeError as e:raise HTTPException(429,detail=str(e))

@router.post('/analyses',status_code=202)
def start(body:Request,background:BackgroundTasks,db:Session=Depends(db_session)):
    provider=body.provider or get_settings().analysis_provider
    try:get_provider(provider)
    except ValueError as e:raise HTTPException(503,detail=str(e))
    if not db.get(CandidateLink,(body.experiment_id,body.source_id,body.target_id)):raise HTTPException(404,detail='Candidate not found')
    owner=acquire_owner()
    if owner is None:raise HTTPException(409,detail='Another analysis is running')
    try:
        recover(db);config=body.model_dump();config['provider']=provider;job=ResearchAnalysis(experiment_id=body.experiment_id,source_id=body.source_id,target_id=body.target_id,status='running',config=config,provider=provider,model_name=None);db.add(job);db.commit();db.refresh(job);background.add_task(execute,job.id,owner);return {'id':job.id,'status':'running'}
    except Exception:release_owner(owner);raise

@router.get('/analyses')
def history(limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0,le=10000),db:Session=Depends(db_session)):
    owner=acquire_owner()
    if owner is not None:
        try:recover(db)
        finally:release_owner(owner)
    rows=db.scalars(select(ResearchAnalysis).order_by(ResearchAnalysis.id.desc()).offset(offset).limit(limit)).all()
    return {'results':[{'id':r.id,'experiment_id':r.experiment_id,'source_id':r.source_id,'target_id':r.target_id,'status':r.status,'review_status':r.synthesis.get('review_status') if r.synthesis else None,'created_at':r.created_at,'error':r.error} for r in rows]}

@router.get('/analyses/{analysis_id}')
def detail(analysis_id:int,db:Session=Depends(db_session)):
    r=db.get(ResearchAnalysis,analysis_id)
    if not r:raise HTTPException(404,detail='Analysis not found')
    return {'id':r.id,'experiment_id':r.experiment_id,'source_id':r.source_id,'target_id':r.target_id,'status':r.status,'config':r.config,'provider':r.provider,'model':r.model_name,'evidence':r.evidence,'synthesis':r.synthesis,'error':r.error,'created_at':r.created_at,'updated_at':r.updated_at}


@router.get('/analyses/{analysis_id}/citations/{citation_id}/verify')
async def verify_citation(analysis_id:int,citation_id:str,db:Session=Depends(db_session)):
    job=db.get(ResearchAnalysis,analysis_id)
    if not job or not job.evidence:raise HTTPException(404,detail='Analysis evidence not found')
    entry=next((p for p in job.evidence.get('papers',[]) if p.get('citation_id')==citation_id),None)
    if not entry:raise HTTPException(404,detail='Citation identifier not found')
    doi=normalize_doi(entry.get('doi'))
    if not doi:return {'citation_id':citation_id,'status':'not_checked','detail':'No valid DOI available; original source not contacted.'}
    # The destination is fixed to doi.org. Never fetch arbitrary publisher URLs or follow redirects.
    url='https://doi.org/'+quote(doi,safe='/')
    try:
        async with httpx.AsyncClient(timeout=8,follow_redirects=False) as client: response=await client.head(url)
        status='resolver_responded' if 200<=response.status_code<400 else 'resolver_unavailable'
        return {'citation_id':citation_id,'status':status,'http_status':response.status_code,'detail':'DOI resolver check only; publisher access, full text and scientific support were not verified.'}
    except httpx.RequestError:
        return {'citation_id':citation_id,'status':'resolver_unavailable','detail':'DOI resolver could not be reached; publisher and full text were not checked.'}
