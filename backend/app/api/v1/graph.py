from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.api.v1.papers import db_session
from app.models.paper import Paper, Topic, Author, PaperTopic, PaperAuthor, Citation

router=APIRouter(prefix='/graph',tags=['graph'])

@router.get('/summary')
def summary(db: Session=Depends(db_session)):
    count=lambda model: db.scalar(select(func.count()).select_from(model))
    citations=db.scalar(select(func.count()).select_from(Citation).join(Paper, Paper.openalex_id==Citation.cited_openalex_id))
    return {'nodes':{'papers':count(Paper),'authors':count(Author),'topics':count(Topic)},'edges':{'authored_by':count(PaperAuthor),'associated_with':count(PaperTopic),'cites':citations},'citation_references_total':count(Citation)}

@router.get('/neighborhood')
def neighborhood(paper_id: int=Query(ge=1), limit: int=Query(50,ge=1,le=100), db: Session=Depends(db_session)):
    paper=db.get(Paper,paper_id)
    if not paper: raise HTTPException(404,detail='Paper not found')
    nodes=[{'id':f'paper:{paper.id}','type':'paper','label':paper.title,'source_url':paper.source_url}]; edges=[]
    authors=db.execute(select(Author,PaperAuthor).join(PaperAuthor,PaperAuthor.author_id==Author.id).where(PaperAuthor.paper_id==paper_id).order_by(PaperAuthor.position).limit(limit)).all()
    for author,link in authors:
        nodes.append({'id':f'author:{author.id}','type':'author','label':author.name,'source_url':author.openalex_id});edges.append({'source':nodes[0]['id'],'target':nodes[-1]['id'],'type':'authored_by','provenance':link.provenance})
    left=max(0,limit-len(edges))
    topics=db.execute(select(Topic,PaperTopic).join(PaperTopic,PaperTopic.topic_id==Topic.id).where(PaperTopic.paper_id==paper_id).limit(left)).all()
    for topic,link in topics:
        nodes.append({'id':f'topic:{topic.id}','type':'topic','label':topic.name,'source_url':None});edges.append({'source':nodes[0]['id'],'target':nodes[-1]['id'],'type':'associated_with','provenance':link.provenance})
    left=max(0,limit-len(edges))
    cited=db.execute(select(Paper,Citation).join(Citation,Citation.cited_openalex_id==Paper.openalex_id).where(Citation.citing_id==paper_id).limit(left)).all()
    for other,link in cited:
        nodes.append({'id':f'paper:{other.id}','type':'paper','label':other.title,'source_url':other.source_url});edges.append({'source':nodes[0]['id'],'target':nodes[-1]['id'],'type':'cites','provenance':link.provenance})
    return {'nodes':nodes,'edges':edges,'limit':limit,'may_be_truncated':len(edges)==limit}
