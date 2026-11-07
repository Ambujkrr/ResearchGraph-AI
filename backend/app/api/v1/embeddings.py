import logging
import threading
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.api.v1.papers import db_session
from app.db.session import SessionLocal
from app.models.paper import Paper, PaperEmbedding
from app.services.embeddings import MODEL, REVISION, DIMENSION, paper_text, content_hash, encode

router=APIRouter(tags=['embeddings'])
lock=threading.Lock()
state={'running':False,'error':None,'processed':0}

def generate(limit):
    try:
        with SessionLocal() as db:
            last_id=0
            remaining=limit
            while remaining:
                # Keyset pagination keeps memory bounded independently of corpus size.
                papers=db.scalars(select(Paper).where(Paper.id>last_id).order_by(Paper.id).limit(64)).all()
                if not papers: break
                last_id=papers[-1].id
                todo=[]
                for p in papers:
                    existing=db.get(PaperEmbedding,(p.id,MODEL,REVISION))
                    if existing is None or existing.content_hash != content_hash(p): todo.append(p)
                    if len(todo)>=remaining: break
                for start in range(0,len(todo),16):
                    batch=todo[start:start+16]; vectors=encode([paper_text(p) for p in batch])
                    for p,v in zip(batch,vectors):
                        if len(v)!=DIMENSION: raise ValueError('Unexpected embedding dimension')
                        entry=db.get(PaperEmbedding,(p.id,MODEL,REVISION))
                        if entry is None: db.add(PaperEmbedding(paper_id=p.id,model_name=MODEL,model_revision=REVISION,content_hash=content_hash(p),vector=v))
                        else: entry.vector=v; entry.content_hash=content_hash(p)
                    db.commit(); state['processed']+=len(batch); remaining-=len(batch)
                db.expunge_all()
    except Exception:
        logging.getLogger(__name__).exception('Embedding generation failed'); state['error']='Embedding generation failed; check backend logs.'
    finally:
        state['running']=False; lock.release()

@router.post('/embeddings/generate',status_code=202)
def start(background: BackgroundTasks, limit:int=Query(100,ge=1,le=500)):
    if not lock.acquire(blocking=False): raise HTTPException(409,detail='Embedding generation already running')
    state.update(running=True,error=None,processed=0); background.add_task(generate,limit)
    return {'status':'started','limit':limit}

@router.get('/embeddings/status')
def status(db:Session=Depends(db_session)):
    total=db.scalar(select(func.count()).select_from(Paper)); count=db.scalar(select(func.count()).select_from(PaperEmbedding).where(PaperEmbedding.model_name==MODEL,PaperEmbedding.model_revision==REVISION))
    return {**state,'papers':total,'embedded':count,'model':MODEL,'revision':REVISION,'dimensions':DIMENSION}

@router.get('/semantic-search')
def search(query:str=Query(min_length=1,max_length=1000),limit:int=Query(10,ge=1,le=25),db:Session=Depends(db_session)):
    if not query.strip(): raise HTTPException(422,detail='Query must not be blank')
    try: vector=encode([query.strip()])[0]
    except Exception: raise HTTPException(503,detail='Embedding model unavailable; check backend logs')
    distance=PaperEmbedding.vector.cosine_distance(vector)
    rows=db.execute(select(Paper, distance.label('distance')).join(PaperEmbedding,Paper.id==PaperEmbedding.paper_id).where(PaperEmbedding.model_name==MODEL,PaperEmbedding.model_revision==REVISION).order_by(distance).limit(limit)).all()
    return {'results':[{'id':p.id,'title':p.title,'source_url':p.source_url,'score':1-float(d)} for p,d in rows]}
