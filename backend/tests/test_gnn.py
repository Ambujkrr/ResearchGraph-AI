import random
import numpy as np
import torch
import networkx as nx
from app.research.gnn import SAGE,split_edges,negative_split,edge_tensor,score_baselines,aggregate_ranks

def test_split_reproducible_and_heldout_absent():
    edges=[(i,i-1) for i in range(1,51)]
    a=split_edges(edges,42);assert a==split_edges(edges,42)
    train,val,test=map(set,a);assert not (train&val or train&test or val&test)
    msg=set(map(tuple,edge_tensor(list(train)).t().tolist()))
    assert all((a,b) not in msg and (b,a) not in msg for a,b in val|test)

def test_negative_constraints():
    years=[2018,2019,2020,2021,2022]*8; observed={(2,1),(3,0)}
    groups=negative_split(years,observed,[8,4,4],21);pairs=[x for group in groups for x in group]
    assert len(pairs)==len(set(pairs)) and not observed.intersection(pairs)
    assert all(a!=b and years[b]<years[a] for a,b in pairs)
    assert groups==negative_split(years,observed,[8,4,4],21)

def test_baseline_values():
    graph=nx.Graph([(0,1),(1,2)]);x=np.array([[1,0],[0,1],[1,0]],dtype=float)
    v=score_baselines([(0,2)],x,graph,{2:3});assert v['cosine'][0]==1 and v['popularity'][0]==3 and v['common_neighbors'][0]==1 and v['adamic_adar'][0]>1
    ranks=aggregate_ranks([[.1,.9,.5]],[[0,1,0]],1);assert ranks['hits_at_k']==1 and ranks['mrr']==1

def test_sage_dimensions_and_checkpoint(tmp_path):
    torch.manual_seed(4);model=SAGE(16,8,0);model.eval();x=torch.rand(5,384);edges=edge_tensor([(1,0),(2,1)]);z=model(x,edges)
    assert z.shape==(5,8) and model.score(z,torch.tensor([[1,0],[2,0]])).shape==(2,)
    p=tmp_path/'m.pt';torch.save(model.state_dict(),p);copy=SAGE(16,8,0);copy.load_state_dict(torch.load(p,weights_only=True));copy.eval();assert torch.allclose(model(x,edges),copy(x,edges))

def test_api_config_validation():
    from fastapi.testclient import TestClient
    from app.main import app
    c=TestClient(app);assert c.get('/api/v1/experiments/configuration').status_code==200
    assert c.post('/api/v1/experiments',json={'epochs':101}).status_code==422


def test_validation_only_reproducible_and_early_stops(tmp_path):
    from app.research.gnn import run
    rng=np.random.default_rng(1);n=35
    years=list(range(1980,1980+n));edges={(i,j) for i in range(1,n) for j in range(max(0,i-3),i)}
    data={'ids':list(range(n)),'years':years,'x':rng.normal(size=(n,384)).astype('float32'),'all_edges':edges,'eligible':sorted(edges),'hash':'test'}
    config={'seed':42,'epochs':6,'hidden':8,'output':8,'dropout':0.0,'learning_rate':.001,'k':10,'candidate_limit':4,'patience':1,'min_delta':.1,'gradient_clip':1.0,'validation_only':True}
    a,c1=run(data,config,str(tmp_path/'a.pt'));b,c2=run(data,config,str(tmp_path/'b.pt'))
    assert a['early_stopped'] and a['epochs_run']<6 and a['best_epoch']==1
    assert a['best_validation_loss']==b['best_validation_loss'] and a['losses']==b['losses']
    assert c1==c2==[] and 'methods' not in a
