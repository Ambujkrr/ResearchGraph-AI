import json
import httpx
import pytest
from app.services.gemini import GeminiProvider,ProviderUnavailable,InvalidGeneration,bounded_context

def evidence(n=4):
    return {'papers':[{'citation_id':f'E{i}','title':f'Paper {i}','abstract':f'Abstract {i}','local':True,'publication_year':2020,'evidence_level':'abstract'} for i in range(1,n+1)]}

def review(status='existing related research found'):
    statement={'text':'The abstracts describe molecular prediction.','citations':['E1','E3']}
    return {'review_status':status,'claims':[statement],'supporting_evidence':[statement],'conflicting_evidence':[],'hypothesis':{'text':'Compare model A to baseline B on molecular pKa error.','citations':['E1','E2']},'validation_experiment':{'text':'Evaluate held-out molecules and report mean absolute error.','citations':['E1']},'uncertainties':[{'text':'Abstracts need full-text review.','citations':['E1']}]}

def transport_for(payload,status=200):
    def handle(request):
        assert request.headers['x-goog-api-key']=='test-secret'
        assert 'test-secret' not in str(request.url)
        return httpx.Response(status,json=payload)
    return httpx.MockTransport(handle)

def wrapped(obj):return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(obj)}]}}],'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':90}}

def test_valid_structured_generation():
    p=GeminiProvider('test-secret',True,transport=transport_for(wrapped(review())))
    output=p.generate(evidence());assert output['generative_synthesis_available'] and output['hypothesis'] and output['citation_validation']['valid']
    assert output['generation_metadata']['model']=='gemini-3.5-flash-lite'

def test_unknown_citation_is_rejected():
    obj=review();obj['claims'][0]['citations']=['E99']
    with pytest.raises(InvalidGeneration):GeminiProvider('test-secret',True,transport=transport_for(wrapped(obj))).generate(evidence())

def test_unknown_embedded_citation_is_rejected():
    obj=review();obj['hypothesis']['text']='Test an idea from E99.'
    with pytest.raises(InvalidGeneration):GeminiProvider('test-secret',True,transport=transport_for(wrapped(obj))).generate(evidence())

def test_malformed_and_http_failure_rejected():
    with pytest.raises(ProviderUnavailable):GeminiProvider('test-secret',True,transport=transport_for({'candidates':[{'content':{'parts':[{'text':'not-json'}]}}]})).generate(evidence())
    with pytest.raises(ProviderUnavailable):GeminiProvider('test-secret',True,transport=transport_for({},429)).generate(evidence())
    with pytest.raises(ProviderUnavailable):GeminiProvider('test-secret',False).generate(evidence())

def test_insufficient_evidence_forces_abstention():
    with pytest.raises(InvalidGeneration):GeminiProvider('test-secret',True,transport=transport_for(wrapped(review()))).generate(evidence(2))
    obj=review('insufficient evidence');obj['claims']=[];obj['supporting_evidence']=[];obj['hypothesis']=None;obj['validation_experiment']=None;obj['uncertainties']=[{'text':'Only two papers were supplied.','citations':['E1','E2']}]
    output=GeminiProvider('test-secret',True,transport=transport_for(wrapped(obj))).generate(evidence(2));assert output['review_status']=='insufficient evidence' and output['hypothesis'] is None

def test_context_is_bounded():
    data=evidence(15)
    for p in data['papers']:p['abstract']='x'*5000
    result=bounded_context(data);assert len(result)<=8 and all(len(x['abstract'])<=1500 for x in result)
