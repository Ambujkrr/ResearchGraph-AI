"""Bounded hybrid evidence retrieval. Retrieval relevance is not evidentiary support."""
import re
from collections import defaultdict
from sqlalchemy import or_,select
from sqlalchemy.orm import Session,aliased
from app.models.paper import Paper,PaperEmbedding,Citation,CandidateLink
from app.services.embeddings import MODEL,REVISION,encode
from app.services.openalex import OpenAlexClient,OpenAlexError,normalize_doi,normalize_id

STOP={'the','and','for','with','from','using','based','graph','neural','networks','network','learning','deep','paper','model','models','towards','via','a','of','to','in','on','an','by','that','this','is','its','are','new','approach'}
def concepts(title):
    return list(dict.fromkeys(w.lower() for w in re.findall(r'[A-Za-z][A-Za-z0-9-]{3,}',title) if w.lower() not in STOP))[:6]

def local_item(p):
    return {'openalex_id':p.openalex_id,'doi':p.doi,'title':p.title,'authors':p.authors or [],'publication_year':p.publication_year,'source_url':p.source_url or p.openalex_id,'abstract':p.abstract,'local':True,'full_text_verified':False}

def external_item(w):
    return {'openalex_id':w['openalex_id'],'doi':w.get('doi'),'title':w['title'],'authors':w.get('authors',[]),'publication_year':w.get('publication_year'),'source_url':w.get('source_url') or w['openalex_id'],'abstract':w.get('abstract'),'local':False,'full_text_verified':False}

def deduplicate(items):
    out=[];ids={};dois={}
    for item in items:
        ident=item.get('openalex_id');doi=normalize_doi(item.get('doi'));idx=ids.get(ident) if ident else None
        if idx is None and doi: idx=dois.get(doi)
        if idx is None:
            idx=len(out);out.append(item.copy());out[-1]['retrieval_methods']=list(dict.fromkeys(item.get('retrieval_methods',[])))
        else:
            out[idx]['retrieval_methods']=list(dict.fromkeys(out[idx]['retrieval_methods']+item.get('retrieval_methods',[])))
        if ident: ids[ident]=idx
        if doi: dois[doi]=idx
    return out

def validate_claims(claims,evidence):
    valid={e['citation_id'] for e in evidence};errors=[]
    for index,claim in enumerate(claims):
        refs=claim.get('citations',[])
        if not refs:errors.append({'claim':index,'error':'missing citation'})
        for ref in refs:
            if ref not in valid: errors.append({'claim':index,'error':'unsupported citation identifier','citation':ref})
    return {'valid':not errors,'errors':errors,'note':'Identifier matching does not establish that a source supports a claim.'}

async def retrieve(db:Session,experiment_id:int,source_id:int,target_id:int,top_k:int,include_external:bool,source:OpenAlexClient):
    candidate=db.get(CandidateLink,(experiment_id,source_id,target_id))
    if candidate is None:raise ValueError('Candidate not found')
    src=db.get(Paper,source_id);tgt=db.get(Paper,target_id)
    if src is None or tgt is None:raise ValueError('Candidate papers not found')
    source_terms=concepts(src.title);target_terms=concepts(tgt.title)
    query=' '.join((source_terms[:4]+target_terms[:4])) or (src.title+' '+tgt.title)[:300]
    scores=defaultdict(float);methods=defaultdict(list);warnings=[]
    def add(rows,method):
        for rank,p in enumerate(rows,1):
            if p.id in (src.id,tgt.id):continue
            scores[p.id]+=1/(60+rank);methods[p.id].append(method)
    try:
        vector=encode([src.title+'\n'+tgt.title])[0]
        distance=PaperEmbedding.vector.cosine_distance(vector)
        rows=db.scalars(select(Paper).join(PaperEmbedding,Paper.id==PaperEmbedding.paper_id).where(PaperEmbedding.model_name==MODEL,PaperEmbedding.model_revision==REVISION).order_by(distance,Paper.id).limit(25)).all()
        add(rows,'semantic_pgvector')
    except Exception:
        # A model or vector query failure should not prevent lexical and citation inspection.
        db.rollback();warnings.append('Semantic retrieval unavailable; lexical and citation retrieval may still work.')
    words=list(dict.fromkeys(source_terms[:4]+target_terms[:4]))[:8]
    if words:
        rows=db.scalars(select(Paper).where(or_(*[Paper.title.ilike('%'+w.replace('%','').replace('_','')+'%') for w in words])).order_by(Paper.id).limit(50)).all()
        # Rank by number of matched title terms, then stable paper ID.
        rows=sorted(rows,key=lambda p:(-sum(w in p.title.lower() for w in words),p.id))[:25];add(rows,'lexical_title')
    other=aliased(Paper)
    rows=db.scalars(select(other).join(Citation,Citation.cited_openalex_id==other.openalex_id).where(Citation.citing_id.in_([source_id,target_id]),Citation.provenance=='openalex').order_by(other.id).limit(25)).all()
    add(rows,'openalex_citation_reference')
    ids=sorted(scores,key=lambda i:(-scores[i],i))[:max(0,top_k-2)]
    byid={p.id:p for p in db.scalars(select(Paper).where(Paper.id.in_(ids))).all()} if ids else {}
    items=[]
    for p,method in [(src,'candidate_source'),(tgt,'candidate_target')]:
        item=local_item(p);item['retrieval_methods']=[method];items.append(item)
    for i in ids:
        item=local_item(byid[i]);item['retrieval_methods']=list(dict.fromkeys(methods[i]));items.append(item)
    if include_external and top_k==2:
        warnings.append('External search skipped: increase the evidence limit above two to allow external results.')
    if include_external and top_k>2:
        try:
            # Exactly one bounded search; no permanent corpus writes.
            result=await source.search(query,1,min(5,top_k))
            for work in result['results']:
                item=external_item(work);item['retrieval_methods']=['openalex_external_search'];items.append(item)
        except OpenAlexError as e:warnings.append('External OpenAlex search unavailable: '+str(e))
    items=deduplicate(items)
    # Preserve candidate pair, then interleave external items when requested within the bound.
    if include_external:
        local=[x for x in items[2:] if x['local']];external=[x for x in items[2:] if not x['local']]
        rest=[]
        while local or external:
            if local:rest.append(local.pop(0))
            if external:rest.append(external.pop(0))
        items=items[:2]+rest
    items=items[:top_k]
    for i,item in enumerate(items,1):
        item['citation_id']=f'E{i}';item['evidence_level']='abstract' if item['abstract'] else 'metadata_only';item['link_check']='not_checked';item['source_attribution']='OpenAlex metadata'
        try:
            normalize_id(item.get('openalex_id'));item['openalex_id_valid']=True
        except ValueError: item['openalex_id_valid']=False
        item['doi_valid']=bool(normalize_doi(item.get('doi')))
        title=item['title'].lower()
        item['source_title_term_matches']=[w for w in source_terms if w in title]
        item['target_title_term_matches']=[w for w in target_terms if w in title]
        item['potential_title_overlap']=bool(item['source_title_term_matches'] and item['target_title_term_matches'])
    return {'candidate':{'experiment_id':experiment_id,'source_id':source_id,'target_id':target_id,'score':candidate.score,'score_label':'uncalibrated model hypothesis','prior_evidence':candidate.evidence},'concepts':{'source_title_terms':source_terms,'target_title_terms':target_terms,'search_query':query},'papers':items,'warnings':warnings,'retrieval_config':{'top_k':top_k,'external_requested':include_external,'external_search_queries':1 if include_external and top_k>2 else 0,'external_max_http_attempts':3 if include_external and top_k>2 else 0,'fusion':'reciprocal rank fusion, k=60; deterministic ID tie break'}}

class GenerationProvider:
    name='unconfigured'
    def generate(self,evidence):raise NotImplementedError

class DeterministicProvider(GenerationProvider):
    name='deterministic_metadata_summary'
    def generate(self,evidence):
        papers=evidence['papers'];related=papers[2:];abstracts=[p for p in related if p.get('abstract')]
        status='insufficient evidence' if not abstracts else 'unable to assess'
        claims=[{'text':f"The retrieved record is titled ‘{p['title']}’"+(f" ({p['publication_year']})" if p.get('publication_year') else '')+'.','citations':[p['citation_id']],'type':'source_metadata'} for p in papers]
        # A question, not a claim of absence, novelty, effectiveness or source support.
        question='Could a future study evaluate the relationship between the methods or questions described in the two candidate papers under a clearly specified task and dataset?' if len(papers)>=2 else None
        return {'review_status':status,'provider':self.name,'generative_synthesis_available':False,'claims':claims,'citation_validation':validate_claims(claims,papers),'potentially_related':[p['citation_id'] for p in related],'supporting_evidence':[],'overlap_or_contradiction':'Not assessed: title-term overlap and retrieval relevance cannot establish scientific overlap or contradiction.','hypothesis':question,'hypothesis_citations':[p['citation_id'] for p in papers[:2]],'validation_experiment':'Define a specific shared task and outcome, review full texts, then compare appropriate baselines on a suitable dataset with a preregistered evaluation.' if question else None,'limitations':['Metadata and abstracts are not full-text verification.','Retrieved papers have not been adjudicated as support, contradiction or prior overlap.','A missing citation edge is not evidence of a research gap.','No generative provider is configured; the hypothesis is a generic question, not a generated novelty claim.']}


PROVIDERS={'deterministic':DeterministicProvider}
def get_provider(name):
    if name=='gemini':
        from app.core.config import get_settings
        from app.services.gemini import GeminiProvider
        settings=get_settings();return GeminiProvider(settings.gemini_api_key,settings.gemini_free_tier_confirmed,settings.gemini_model)
    cls=PROVIDERS.get(name)
    if cls is None: raise ValueError('Generation provider is not configured or available')
    return cls()
