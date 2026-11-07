import logging, threading
from typing import Literal
from pathlib import Path
from fastapi import APIRouter,BackgroundTasks,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import exists, select, text, update
from sqlalchemy.orm import Session, aliased
from app.api.v1.papers import db_session
from app.db.session import SessionLocal, engine
from app.models.paper import Experiment,CandidateLink,Paper,Citation

router=APIRouter(prefix='/experiments',tags=['experiments'])
lock=threading.Lock()
ADVISORY_KEY=726273150

def acquire_owner():
    if not lock.acquire(False): return None
    connection=None
    try:
        connection=engine.connect()
        if connection.dialect.name!='postgresql':
            connection.close();lock.release();raise RuntimeError('Experiment execution requires PostgreSQL')
        acquired=connection.scalar(text('select pg_try_advisory_lock(:key)'),{'key':ADVISORY_KEY})
        connection.commit()
        if not acquired: connection.close();lock.release();return None
        return connection
    except Exception:
        if connection is not None: connection.close()
        if lock.locked(): lock.release()
        raise

def release_owner(connection):
    try:
        connection.execute(text('select pg_advisory_unlock(:key)'),{'key':ADVISORY_KEY});connection.commit()
    finally:
        connection.close();lock.release()

def mark_interrupted(db):
    db.execute(update(Experiment).where(Experiment.status=='running').values(status='interrupted',error='Worker ended before completing; start a new experiment.'))
    db.commit()

class Config(BaseModel):
    seed:int=Field(42,ge=0,le=1000000)
    epochs:int=Field(30,ge=1,le=100)
    hidden:int=Field(64,ge=8,le=128)
    output:int=Field(32,ge=8,le=64)
    dropout:float=Field(.1,ge=0,le=.5)
    learning_rate:float=Field(.005,gt=0,le=.05)
    k:int=Field(10,ge=1,le=50)
    candidate_limit:int=Field(100,ge=1,le=200)
    patience:int=Field(6,ge=1,le=30)
    min_delta:float=Field(.0001,ge=0,le=.1)
    gradient_clip:float=Field(1.0,gt=0,le=10)
    domain_filter:bool=False

@router.get('/configuration')
def configuration(): return {'defaults':Config().model_dump(),'evaluation':'Exploratory random edge holdout; not a historical forecast','thread_limit':2,'node_limit':1000}

def execute(id,owner):
    try:
        from app.research.gnn import load_dataset,run
        with SessionLocal() as db:
            job=db.get(Experiment,id);config=job.config
            dataset=load_dataset(db,[301,396,445,504] if config.get('domain_filter') else None);job.dataset_hash=dataset['hash'];db.commit()
        def progress(epoch,total,loss):
            with SessionLocal() as db:
                job=db.get(Experiment,id);job.metrics={'progress':{'epoch':epoch,'total_epochs':total,**loss}};db.commit()
        path=str(Path('/app/artifacts')/f'experiment-{id}.pt')
        metrics,candidates=run(dataset,config,path,progress)
        with SessionLocal() as db:
            job=db.get(Experiment,id);job.metrics=metrics;job.status='completed'
            db.add_all([CandidateLink(experiment_id=id,source_id=c['source_id'],target_id=c['target_id'],rank=i+1,score=c['score'],popularity_score=c.get('popularity_score'),popularity_rank=c.get('popularity_rank'),evidence=c.get('evidence')) for i,c in enumerate(candidates)]);db.commit()
    except Exception:
        logging.getLogger(__name__).exception('Experiment failed')
        with SessionLocal() as db:
            job=db.get(Experiment,id)
            if job:job.status='failed';job.error='Experiment failed; see backend logs.';db.commit()
    finally:release_owner(owner)

@router.post('',status_code=202)
def start(config:Config,background:BackgroundTasks,db:Session=Depends(db_session)):
    owner=acquire_owner()
    if owner is None: raise HTTPException(409,detail='Another experiment is running')
    try:
        mark_interrupted(db)
        job=Experiment(status='running',config=config.model_dump());db.add(job);db.commit();db.refresh(job);background.add_task(execute,job.id,owner);return {'id':job.id,'status':job.status}
    except Exception: release_owner(owner);raise

@router.get('')
def list_experiments(limit:int=Query(20,ge=1,le=100),db:Session=Depends(db_session)):
    owner=acquire_owner()
    if owner is not None:
        try: mark_interrupted(db)
        finally: release_owner(owner)
    rows=db.scalars(select(Experiment).order_by(Experiment.id.desc()).limit(limit)).all()
    return {'results':[{'id':r.id,'status':r.status,'config':r.config,'dataset_hash':r.dataset_hash,'metrics':r.metrics,'error':r.error,'created_at':r.created_at} for r in rows]}

@router.get('/{experiment_id}')
def detail(experiment_id:int,db:Session=Depends(db_session)):
    r=db.get(Experiment,experiment_id)
    if not r:raise HTTPException(404,detail='Experiment not found')
    return {'id':r.id,'status':r.status,'config':r.config,'dataset_hash':r.dataset_hash,'metrics':r.metrics,'error':r.error,'created_at':r.created_at}

@router.get('/{experiment_id}/candidates')
def candidates(experiment_id:int,limit:int=Query(25,ge=1,le=100),offset:int=Query(0,ge=0,le=10000),sort:Literal['model','popularity']='model',db:Session=Depends(db_session)):
    if not db.get(Experiment,experiment_id): raise HTTPException(404,detail='Experiment not found')
    target=aliased(Paper)
    observed=exists(select(Citation.citing_id).join(target,target.openalex_id==Citation.cited_openalex_id).where(Citation.citing_id==CandidateLink.source_id,target.id==CandidateLink.target_id))
    ordering=CandidateLink.rank if sort=='model' else CandidateLink.popularity_rank.asc().nullslast()
    links=db.scalars(select(CandidateLink).where(CandidateLink.experiment_id==experiment_id,~observed).order_by(ordering,CandidateLink.rank).offset(offset).limit(limit)).all()
    results=[]
    for link in links:
        source=db.get(Paper,link.source_id);target=db.get(Paper,link.target_id)
        results.append({'rank':link.rank,'source':{'id':source.id,'title':source.title,'openalex_id':source.openalex_id,'source_url':source.source_url},'target':{'id':target.id,'title':target.title,'openalex_id':target.openalex_id,'source_url':target.source_url},'score':link.score,'popularity_score':link.popularity_score,'popularity_rank':link.popularity_rank,'evidence':link.evidence,'label':'hypothesis; uncalibrated score, not a verified citation'})
    return {'results':results,'offset':offset,'limit':limit,'sort':sort,'scope':'popularity reorders the saved model-selected candidate set'}
