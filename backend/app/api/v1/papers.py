from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.paper import Paper, IngestionRun, Topic, PaperTopic
from app.services.graph import save_work
from app.services.openalex import OpenAlexClient, OpenAlexError, normalize_id

router=APIRouter(tags=['papers'])
def db_session():
    with SessionLocal() as db: yield db

def client(): return OpenAlexClient(get_settings().openalex_api_key)

class IngestRequest(BaseModel):
    topic: str = Field(min_length=1,max_length=200)
    ids: list[str] = Field(min_length=1,max_length=10)
    @field_validator('topic')
    @classmethod
    def topic_nonblank(cls,v):
        if not v.strip(): raise ValueError('Topic must not be blank')
        return v.strip()
    @field_validator('ids')
    @classmethod
    def ids_valid(cls,v): return list(dict.fromkeys(normalize_id(x) for x in v))

class PaperOut(BaseModel):
    id: int | None = None
    openalex_id: str
    title: str
    abstract: str | None
    publication_date: date | None
    publication_year: int | None
    authors: list
    citation_count: int | None
    doi: str | None
    source_url: str | None
    topic: str | None = None
    ingested_at: datetime | None = None
    model_config={'from_attributes':True}

@router.get('/openalex/search')
async def search(topic: Annotated[str, Query(min_length=1,max_length=200)], page: int=Query(1,ge=1,le=50), per_page: int=Query(10,ge=1,le=25), source: OpenAlexClient=Depends(client)):
    if not topic.strip(): raise HTTPException(422,detail='Topic must not be blank')
    try:
        result=await source.search(topic.strip(),page,per_page)
        result['results']=[PaperOut(**p) for p in result['results']]
        return result
    except OpenAlexError as e: raise HTTPException(e.status, detail=str(e))

@router.post('/papers/ingest')
async def ingest(request: IngestRequest, db: Session=Depends(db_session), source: OpenAlexClient=Depends(client)):
    run=IngestionRun(topic=request.topic,status='running',requested=len(request.ids),saved=0); db.add(run); db.commit(); db.refresh(run)
    try:
        # Fetch before opening the bounded write transaction; never trust client-supplied metadata.
        works=[await source.work(i) for i in request.ids]
        for requested, work in zip(request.ids, works):
            if work['openalex_id'] != requested: raise ValueError('Unexpected upstream ID')
        for w in works: save_work(db,w,request.topic)
        run.status='completed'; run.saved=len(works); db.commit()
        return {'run_id':run.id,'status':run.status,'processed':len(works)}
    except (OpenAlexError,ValueError,IntegrityError) as e:
        db.rollback(); run=db.get(IngestionRun,run.id); run.status='failed'; run.error='Conflicting identifiers or invalid upstream data' if isinstance(e,(ValueError,IntegrityError)) else str(e); db.commit()
        raise HTTPException(e.status if isinstance(e,OpenAlexError) else 409,detail={'run_id':run.id,'message':run.error})

@router.get('/papers')
def list_papers(page: int=Query(1,ge=1,le=10000), per_page: int=Query(10,ge=1,le=100), topic: str | None=Query(None,max_length=200), year: int | None=Query(None,ge=1000,le=3000), db: Session=Depends(db_session)):
    filters=[]
    if topic and topic.strip(): filters.append(Paper.id.in_(select(PaperTopic.paper_id).join(Topic, Topic.id==PaperTopic.topic_id).where(Topic.normalized_name.ilike('%'+topic.strip().casefold().replace('!', '!!').replace('%','!%').replace('_','!_')+'%',escape='!'))))
    if year: filters.append(Paper.publication_year==year)
    total=db.scalar(select(func.count()).select_from(Paper).where(*filters))
    papers=db.scalars(select(Paper).where(*filters).order_by(Paper.id.desc()).offset((page-1)*per_page).limit(per_page)).all()
    return {'results':[PaperOut.model_validate(p) for p in papers], 'total':total,'page':page,'per_page':per_page}

@router.get('/papers/{paper_id}', response_model=PaperOut)
def get_paper(paper_id: int, db: Session=Depends(db_session)):
    paper=db.get(Paper,paper_id)
    if not paper: raise HTTPException(404,detail='Paper not found')
    return paper

@router.get('/ingestions')
def runs(page: int=Query(1,ge=1,le=10000), per_page: int=Query(10,ge=1,le=100), db: Session=Depends(db_session)):
    db.execute(update(IngestionRun).where(IngestionRun.status=='running',IngestionRun.created_at < datetime.now(timezone.utc)-timedelta(hours=1)).values(status='interrupted',error='The ingestion process was interrupted; retry the selected papers.'))
    db.commit()
    rows=db.scalars(select(IngestionRun).order_by(IngestionRun.id.desc()).offset((page-1)*per_page).limit(per_page)).all()
    return {'results':[{'id':r.id,'topic':r.topic,'status':r.status,'requested':r.requested,'saved':r.saved,'error':r.error,'created_at':r.created_at} for r in rows], 'total':db.scalar(select(func.count()).select_from(IngestionRun)), 'page':page,'per_page':per_page}
