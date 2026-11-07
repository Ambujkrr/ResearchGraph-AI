"""Exploratory non-temporal citation prediction. No held-out edge enters message passing."""
import hashlib, json, math, random, time, os
from collections import defaultdict
import numpy as np
import torch
import torch.nn.functional as F
import networkx as nx
from sklearn.metrics import roc_auc_score, average_precision_score
from torch import nn
from torch_geometric.nn import SAGEConv
from sqlalchemy import select
from app.models.paper import Paper, PaperEmbedding, Citation
from app.services.embeddings import MODEL, REVISION, content_hash

class SAGE(nn.Module):
    def __init__(self, hidden=64, output=32, dropout=0.1):
        super().__init__(); self.conv1=SAGEConv(384,hidden); self.conv2=SAGEConv(hidden,output); self.source=nn.Linear(output,output,bias=False); self.target=nn.Linear(output,output,bias=False); self.dropout=dropout
    def forward(self,x,edge_index):
        h=F.relu(self.conv1(x,edge_index)); h=F.dropout(h,p=self.dropout,training=self.training); return self.conv2(h,edge_index)
    def score(self,z,pairs):
        return (self.source(z[pairs[:,0]])*self.target(z[pairs[:,1]])).sum(dim=1)

def load_dataset(db,excluded_ids=None):
    rows=db.execute(select(Paper,PaperEmbedding).join(PaperEmbedding,PaperEmbedding.paper_id==Paper.id).where(PaperEmbedding.model_name==MODEL,PaperEmbedding.model_revision==REVISION).order_by(Paper.id)).all()
    excluded=set(excluded_ids or [])
    rows=[(p,e) for p,e in rows if p.id not in excluded]
    if not rows: raise ValueError('No matching embeddings exist')
    if len(rows)>1000: raise ValueError('Experiment limit is 1000 papers')
    if any(p.publication_year is None or content_hash(p)!=e.content_hash for p,e in rows): raise ValueError('Missing publication year or stale vector')
    ids=[p.id for p,e in rows]; years=[p.publication_year for p,e in rows]; idx={p.openalex_id:i for i,(p,e) in enumerate(rows)}; ididx={id:i for i,id in enumerate(ids)}
    all_edges=set()
    for source,target in db.execute(select(Citation.citing_id,Citation.cited_openalex_id).where(Citation.provenance=='openalex')):
        if source in ididx and target in idx and ididx[source]!=idx[target]: all_edges.add((ididx[source],idx[target]))
    eligible=sorted((a,b) for a,b in all_edges if years[b]<years[a])
    x=np.asarray([e.vector for p,e in rows],dtype=np.float32)
    h=hashlib.sha256();h.update(json.dumps({'ids':ids,'years':years,'edges':sorted(all_edges),'model':MODEL,'revision':REVISION},sort_keys=True,separators=(',',':')).encode());h.update(x.tobytes())
    return {'ids':ids,'years':years,'x':x,'all_edges':all_edges,'eligible':eligible,'hash':h.hexdigest()}

def split_edges(edges,seed):
    values=list(sorted(edges)); random.Random(seed).shuffle(values)
    n=len(values); ntest=max(1,int(n*.15)); nval=max(1,int(n*.15))
    if n<20: raise ValueError('Not enough eligible citation edges')
    return values[nval+ntest:],values[:nval],values[nval:nval+ntest]

def eligible_unobserved(years,observed):
    return [(i,j) for i,y in enumerate(years) for j,ty in enumerate(years) if i!=j and ty<y and (i,j) not in observed]

def negative_split(years,observed,counts,seed):
    pool=eligible_unobserved(years,observed);random.Random(seed).shuffle(pool)
    if sum(counts)>len(pool): raise ValueError('Insufficient unlabeled pairs')
    result=[];i=0
    for n in counts: result.append(pool[i:i+n]);i+=n
    return result

def tensor_pairs(pairs): return torch.tensor(pairs,dtype=torch.long).reshape(-1,2)
def edge_tensor(train):
    # Undirected message passing over training citations only. Decoder is directional.
    links=train+[(b,a) for a,b in train]
    return torch.tensor(links,dtype=torch.long).t().contiguous()

def score_baselines(pairs,x,graph,indegree):
    cos=[];pop=[];cn=[];aa=[]
    for a,b in pairs:
        va=x[a];vb=x[b];den=float(np.linalg.norm(va)*np.linalg.norm(vb));cos.append(float(va@vb/den) if den else 0.0)
        pop.append(float(indegree.get(b,0)))
        common=set(graph.neighbors(a)) & set(graph.neighbors(b));cn.append(float(len(common)));aa.append(float(sum(1/math.log(graph.degree(n)) for n in common if graph.degree(n)>1)))
    return {'cosine':cos,'popularity':pop,'common_neighbors':cn,'adamic_adar':aa}

def aggregate_ranks(scores,labels,k):
    if not scores: return {'queries':0,'precision_at_k':None,'recall_at_k':None,'hits_at_k':None,'mrr':None}
    results=[]
    for s,y in zip(scores,labels):
        order=np.argsort(-np.asarray(s),kind='stable'); y=np.asarray(y)[order]; top=y[:k];n=int(y.sum())
        positions=np.flatnonzero(y);results.append((float(top.sum()/min(k,len(y))),float(top.sum()/n),float(top.sum()>0),1.0/(int(positions[0])+1)))
    return {'queries':len(results),'precision_at_k':float(np.mean([x[0] for x in results])),'recall_at_k':float(np.mean([x[1] for x in results])),'hits_at_k':float(np.mean([x[2] for x in results])),'mrr':float(np.mean([x[3] for x in results]))}

def run(dataset,config,checkpoint_path,progress=lambda *args:None):
    t0=time.monotonic();seed=config['seed'];random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.set_num_threads(2)
    ids,years,x,known=dataset['ids'],dataset['years'],dataset['x'],dataset['all_edges'];train,val,test=split_edges(dataset['eligible'],seed)
    train_neg,val_neg,test_neg=negative_split(years,known,[len(train),len(val),len(test)],seed+1)
    graph=nx.Graph();graph.add_nodes_from(range(len(ids)));graph.add_edges_from(train); indegree=defaultdict(int)
    for a,b in train: indegree[b]+=1
    xt=torch.tensor(x,dtype=torch.float32);eidx=edge_tensor(train);model=SAGE(config['hidden'],config['output'],config['dropout']);optimizer=torch.optim.Adam(model.parameters(),lr=config['learning_rate'])
    trp=tensor_pairs(train+train_neg);try_=torch.tensor([1.]*len(train)+[0.]*len(train_neg));vap=tensor_pairs(val+val_neg);vay=torch.tensor([1.]*len(val)+[0.]*len(val_neg));best=None;best_loss=float('inf');best_epoch=0;wait=0;losses=[]
    patience=config.get('patience',6);min_delta=config.get('min_delta',0.0001);clip_norm=config.get('gradient_clip',1.0)
    for epoch in range(config['epochs']):
        model.train();optimizer.zero_grad();z=model(xt,eidx);loss=F.binary_cross_entropy_with_logits(model.score(z,trp),try_);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),clip_norm);optimizer.step()
        model.eval()
        with torch.no_grad(): z=model(xt,eidx);vl=F.binary_cross_entropy_with_logits(model.score(z,vap),vay).item()
        losses.append({'epoch':epoch+1,'train':float(loss.item()),'validation':float(vl)})
        if vl<best_loss-min_delta:
            best_loss=vl;best_epoch=epoch+1;wait=0;best={k:v.detach().clone() for k,v in model.state_dict().items()}
        else: wait+=1
        progress(epoch+1,config['epochs'],losses[-1])
        if wait>=patience: break
    model.load_state_dict(best);model.eval()
    if config.get('validation_only',False):
        return {'best_validation_loss':best_loss,'best_epoch':best_epoch,'epochs_run':len(losses),'early_stopped':len(losses)<config['epochs'],'losses':losses,'dataset_hash':dataset['hash'],'methodology':'validation only; no test metrics used'},[]
    with torch.no_grad(): z=model(xt,eidx);sample_pairs=test+test_neg;gnn=model.score(z,tensor_pairs(sample_pairs)).numpy().tolist()
    baseline=score_baselines(sample_pairs,x,graph,indegree);baseline['graphsage']=gnn;labels=[1]*len(test)+[0]*len(test_neg)
    methods={name:{'roc_auc':float(roc_auc_score(labels,v)),'average_precision':float(average_precision_score(labels,v))} for name,v in baseline.items()}
    grouped=defaultdict(set)
    for a,b in test: grouped[a].add(b)
    all_rank={name:[] for name in methods}; ys=[]; cold=[]
    for source,truth in sorted(grouped.items()):
        targets=[t for t,y in enumerate(years) if t!=source and y<years[source] and ((source,t) not in known or t in truth)]
        pairs=[(source,t) for t in targets];y=[int(t in truth) for t in targets]
        if not pairs:continue
        vals=score_baselines(pairs,x,graph,indegree)
        with torch.no_grad(): vals['graphsage']=model.score(z,tensor_pairs(pairs)).numpy().tolist()
        for name in methods:all_rank[name].append(vals[name])
        ys.append(y);cold.append(graph.degree(source)==0)
    k=config['k']
    for name in methods:
        methods[name]['ranking']=aggregate_ranks(all_rank[name],ys,k)
        for label,flag in [('cold_start',True),('connected',False)]:
            indices=[i for i,v in enumerate(cold) if v==flag];methods[name][label]=aggregate_ranks([all_rank[name][i] for i in indices],[ys[i] for i in indices],k)
    possible=eligible_unobserved(years,known); rankings=[]
    with torch.no_grad():
        for start in range(0,len(possible),4096):
            pairs=possible[start:start+4096]; scores=model.score(z,tensor_pairs(pairs)).tolist();rankings.extend((float(score),a,b) for score,(a,b) in zip(scores,pairs))
    rankings.sort(key=lambda row:(-row[0],row[1],row[2])); candidates=[];per_source=defaultdict(int)
    for score,a,b in rankings:
        if per_source[a]>=3:continue
        candidates.append({'source_id':ids[a],'target_id':ids[b],'score':score});per_source[a]+=1
        if len(candidates)>=config['candidate_limit']:break
    pop_order=sorted(possible,key=lambda p:(-indegree.get(p[1],0),p[0],p[1])); pop_rank={p:i+1 for i,p in enumerate(pop_order)}
    for candidate in candidates:
        a=ids.index(candidate['source_id']); b=ids.index(candidate['target_id']); evidence=score_baselines([(a,b)],x,graph,indegree)
        candidate['popularity_score']=indegree.get(b,0);candidate['popularity_rank']=pop_rank[(a,b)]
        candidate['evidence']={'target_training_in_degree':indegree.get(b,0),'training_common_neighbors':int(evidence['common_neighbors'][0]),'embedding_cosine':evidence['cosine'][0],'source_year':years[a],'target_year':years[b],'message':'training-graph and current-text evidence; not proof of a missing citation'}
    os.makedirs(os.path.dirname(checkpoint_path),exist_ok=True)
    temp_path=checkpoint_path+'.tmp'
    torch.save({'model_state':model.state_dict(),'config':config,'dataset_hash':dataset['hash'],'paper_ids':ids,'train_edges':[[ids[a],ids[b]] for a,b in train],'validation_edges':[[ids[a],ids[b]] for a,b in val],'test_edges':[[ids[a],ids[b]] for a,b in test],'model_name':MODEL,'model_revision':REVISION},temp_path)
    os.replace(temp_path,checkpoint_path)
    metrics={'methodology':'exploratory random edge split, NOT a future citation forecast','node_count':len(ids),'observed_edges':len(known),'eligible_positive_edges':len(dataset['eligible']),'excluded_same_or_later_year_edges':len(known)-len(dataset['eligible']),'train_positives':len(train),'validation_positives':len(val),'test_positives':len(test),'sampled_test_unlabeled':len(test_neg),'evaluation_k':k,'ranking_candidates':'all older-year local papers excluding observed edges other than the source test positives','test_source_queries':len(ys),'cold_start_sources':sum(cold),'methods':methods,'losses':losses,'runtime_seconds':time.monotonic()-t0,'candidate_count':len(candidates),'best_epoch':best_epoch,'best_validation_loss':best_loss,'epochs_run':len(losses),'early_stopped':len(losses)<config['epochs'],'patience':patience,'gradient_clip':clip_norm}
    return metrics,candidates
