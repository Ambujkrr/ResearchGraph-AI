"""Persist only identities and relationships supplied by OpenAlex or ingestion queries."""
import re
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session
from app.models.paper import Paper, Author, Topic, PaperAuthor, PaperTopic, Citation, PaperEmbedding

def associate(db: Session, paper, topic: str, citations: list[str]):
    name=' '.join(topic.split()); normalized=name.casefold()
    entity=db.scalar(select(Topic).where(Topic.normalized_name==normalized))
    if not entity:
        entity=Topic(name=name,normalized_name=normalized); db.add(entity); db.flush()
    if not db.get(PaperTopic,(paper.id,entity.id)):
        db.add(PaperTopic(paper_id=paper.id,topic_id=entity.id,provenance='ingestion_query'))
    seen_author_ids=set()
    for position,item in enumerate(paper.authors or [],start=1):
        ident=item.get('openalex_id'); name=item.get('name')
        if not isinstance(ident,str) or not re.fullmatch(r'https://openalex\.org/A[0-9]+',ident) or not isinstance(name,str) or not name.strip(): continue
        if ident in seen_author_ids: continue
        seen_author_ids.add(ident)
        author=db.scalar(select(Author).where(Author.openalex_id==ident))
        if not author:
            author=Author(openalex_id=ident,name=name.strip()); db.add(author); db.flush()
        if not db.get(PaperAuthor,(paper.id,author.id)):
            db.add(PaperAuthor(paper_id=paper.id,author_id=author.id,position=position,provenance='openalex'))
    for cited in set(citations):
        if not db.get(Citation,(paper.id,cited)):
            db.add(Citation(citing_id=paper.id,cited_openalex_id=cited,provenance='openalex'))


def save_work(db: Session, work: dict, topic: str):
    w=work.copy(); citations=w.pop('referenced_works', [])
    match=or_(Paper.openalex_id==w['openalex_id'],Paper.normalized_doi==w['normalized_doi']) if w['normalized_doi'] else Paper.openalex_id==w['openalex_id']
    existing=db.scalar(select(Paper).where(match))
    if existing:
        if w['normalized_doi'] and db.scalar(select(Paper).where(Paper.normalized_doi==w['normalized_doi'],Paper.id != existing.id)):
            raise ValueError('Conflicting identifiers')
        w['openalex_id']=existing.openalex_id
        if existing.title != w['title'] or existing.abstract != w['abstract']:
            db.execute(delete(PaperEmbedding).where(PaperEmbedding.paper_id==existing.id))
        for key,val in w.items(): setattr(existing,key,val)
        existing.topic=topic
    else:
        existing=Paper(**w,topic=topic);db.add(existing)
    db.flush();associate(db,existing,topic,citations);db.flush()
    return existing
