import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.api.v1.papers import db_session
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.paper import CollectionJob
from app.services.openalex import OpenAlexClient
from app.services.graph import save_work

router=APIRouter(prefix='/collections',tags=['collections'])
lock=threading.Lock()
class Request(BaseModel):
    topic:str=Field(min_length=1,max_length=200)
    target:int=Field(default=500,ge=1,le=1000)
    @field_validator('topic')
    @classmethod
    def nonblank(cls,v):
        if not v.strip(): raise ValueError('Topic is required')
        return v.strip()

def execute(job_id):
    try:
        with SessionLocal() as db:
            job=db.get(CollectionJob,job_id)
            while job.processed<job.target:
                per_page=25
                result=asyncio.run(OpenAlexClient(get_settings().openalex_api_key).search(job.topic,job.next_page,per_page))
                remaining=job.target-job.processed
                for work in result['results'][:remaining]: save_work(db,work,job.topic)
                job.processed+=min(len(result['results']),remaining); job.next_page+=1
                if not result['results'] or len(result['results'])<per_page: job.status='completed';db.commit();return
                db.commit()
            job.status='completed';db.commit()
    except Exception:
        logging.getLogger(__name__).exception('Collection failed')
        with SessionLocal() as db:
            job=db.get(CollectionJob,job_id)
            if job: job.status='failed';job.error='Collection failed; see backend logs.';db.commit()
    finally: lock.release()

@router.post('',status_code=202)
def start(body:Request,background:BackgroundTasks,db:Session=Depends(db_session)):
    if not lock.acquire(False): raise HTTPException(409,detail='Collection already running')
    try:
        job=CollectionJob(topic=body.topic,target=body.target,processed=0,next_page=1,status='running');db.add(job);db.commit();db.refresh(job)
        background.add_task(execute,job.id);return {'id':job.id,'status':job.status}
    except Exception: lock.release();raise

@router.post('/{job_id}/resume',status_code=202)
def resume(job_id:int,background:BackgroundTasks,db:Session=Depends(db_session)):
    job=db.get(CollectionJob,job_id)
    if not job: raise HTTPException(404,detail='Collection not found')
    if job.status not in ('failed','interrupted'): raise HTTPException(409,detail='Collection is not resumable')
    if not lock.acquire(False): raise HTTPException(409,detail='Collection already running')
    try:
        job.status='running';job.error=None;db.commit();background.add_task(execute,job.id);return {'id':job.id,'status':job.status}
    except Exception: lock.release();raise

@router.get('')
def list_jobs(limit:int=Query(20,ge=1,le=100),db:Session=Depends(db_session)):
    db.execute(update(CollectionJob).where(CollectionJob.status=='running',CollectionJob.updated_at < datetime.now(timezone.utc)-timedelta(minutes=10)).values(status='interrupted',error='Collection heartbeat expired; resume from its last checkpoint.'))
    db.commit()
    jobs=db.scalars(select(CollectionJob).order_by(CollectionJob.id.desc()).limit(limit)).all()
    return {'results':[{'id':j.id,'topic':j.topic,'target':j.target,'processed':j.processed,'next_page':j.next_page,'status':j.status,'error':j.error} for j in jobs]}
