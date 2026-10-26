import json
import os
from pathlib import Path

import httpx
import pytest
from devtriage.config import Settings, PROJECT
from devtriage.knowledge import (Document, KnowledgeArgs, KnowledgeSearch, KnowledgeStore,
                                Embeddings, bm25, chunks, ingest, vector_checked)
from devtriage.models import DiagnosisRequest
from devtriage.agent import diagnose


class FakeEmbeddings:
    available = True
    fingerprint = "test-model-1"

    async def encode(self, texts):
        # A deterministic semantic channel fixture, not a real-model accuracy claim.
        return [[1.,0.] if any(t in text for t in ("Hikari", "pool", "数据库等待")) else [0.,1.] for text in texts]


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path/'state')


@pytest.fixture
def source(tmp_path):
    path = tmp_path/'knowledge.json'
    path.write_text(json.dumps([
        dict(id="pool",title="Hikari pool",source="curated://pool",revision="1",component="hikari",versions=["5"],content="Connection is not available\n检查连接池耗尽与慢SQL。 password=private-value"),
        dict(id="redis",title="Redis TTL",source="curated://redis",revision="1",component="redis",repository="team-a",content="缓存过期回源，需要检查TTL。")
    ],ensure_ascii=False),encoding='utf-8')
    return path


async def test_keyword_chinese_scope_and_no_match(settings, source):
    assert (await ingest(settings,source))["mode"] == "keyword"
    search = KnowledgeSearch(settings,"team-b")
    result = await search.search(KnowledgeArgs(query="连接池耗尽"))
    assert result['mode']=='keyword'
    ref=result['matches'][0]['reference']
    assert ref['document_id']=='pool' and 'private-value' not in ref['text']
    assert search.validate([ref['id']])[0].revision=='1'
    assert not (await search.search(KnowledgeArgs(query='Redis TTL')))['matches']
    assert not (await search.search(KnowledgeArgs(query='ZebraQuantumException')))['matches']
    assert not (await search.search(KnowledgeArgs(query='Hikari',version='6')))['matches']
    assert not (await search.search(KnowledgeArgs(query='Hikari',component='redis')))['matches']


async def test_hybrid_semantic_only_and_threshold(settings,source):
    embedder=FakeEmbeddings()
    await ingest(settings,source,embedder=embedder)
    search=KnowledgeSearch(settings,'team-b',embedder)
    assert not (await search.search(KnowledgeArgs(query='数据库等待',mode='keyword')))['matches']
    result=await search.search(KnowledgeArgs(query='数据库等待'))
    assert result['mode']=='hybrid' and result['matches'][0]['reference']['document_id']=='pool'
    assert result['matches'][0]['keyword_score'] is None
    assert not (await search.search(KnowledgeArgs(query='unrelated',mode='dense')))['matches']


async def test_update_prune_and_stale_citations(settings,source):
    await ingest(settings,source)
    search=KnowledgeSearch(settings,'team-a')
    ref=(await search.search(KnowledgeArgs(query='Hikari')))['matches'][0]['reference']
    await ingest(settings,source)
    assert search.validate([ref['id']])  # idempotent reindex
    data=json.loads(source.read_text(encoding='utf-8'))[:1]
    data[0]['revision']='2'
    data[0]['content']='Updated pool manual'
    source.write_text(json.dumps(data),encoding='utf-8')
    await ingest(settings,source)
    with pytest.raises(ValueError,match='stale'):
        search.validate([ref['id']])
    with pytest.raises(ValueError):
        search.validate(['invented'])
    assert not (await search.search(KnowledgeArgs(query='TTL')))['matches']


async def test_index_failure_is_atomic(settings,source):
    await ingest(settings,source)
    data=json.loads(source.read_text(encoding='utf-8')); data.append(data[0])
    source.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='Duplicate'):
        await ingest(settings,source)
    assert (await KnowledgeSearch(settings,'global').search(KnowledgeArgs(query='Hikari')))['matches']


async def test_incremental_embeddings_and_failed_update(settings,source):
    embedder=FakeEmbeddings()
    first=await ingest(settings,source,embedder=embedder)
    assert first['embedded_chunks']==2
    second=await ingest(settings,source,embedder=embedder)
    assert second['embedded_chunks']==0 and second['reused_embeddings']==2
    data=json.loads(source.read_text(encoding='utf-8'));data[0]['revision']='2'
    source.write_text(json.dumps(data),encoding='utf-8')
    class Broken(FakeEmbeddings):
        async def encode(self,texts): raise ValueError('provider unavailable')
    with pytest.raises(ValueError):
        await ingest(settings,source,embedder=Broken())
    result=await KnowledgeSearch(settings,'global',embedder).search(KnowledgeArgs(query='Hikari'))
    assert result['matches'][0]['reference']['revision']=='1'
    result=await ingest(settings,source,embedder=embedder)
    assert result['embedded_chunks']==1 and result['reused_embeddings']==1


async def test_rrf_combines_independent_rankings(settings,source):
    embedder=FakeEmbeddings()
    await ingest(settings,source,embedder=embedder)
    result=await KnowledgeSearch(settings,'team-a',embedder).search(KnowledgeArgs(query='Hikari pool'))
    match=result['matches'][0]
    assert match['reference']['document_id']=='pool'
    assert match['keyword_score']>0 and match['cosine_similarity']==pytest.approx(1)
    assert match['rrf_score']==pytest.approx(2/61)


async def test_embedding_failure_and_model_change_fallback(settings,source):
    embedder=FakeEmbeddings()
    await ingest(settings,source,embedder=embedder)
    class Broken(FakeEmbeddings):
        async def encode(self,texts): raise ValueError('unavailable')
    result=await KnowledgeSearch(settings,'global',Broken()).search(KnowledgeArgs(query='Hikari'))
    assert result['mode']=='keyword' and result['warning'].startswith('embedding_unavailable')
    embedder.fingerprint='different-model'
    result=await KnowledgeSearch(settings,'global',embedder).search(KnowledgeArgs(query='Hikari'))
    assert result['mode']=='keyword' and result['warning'].startswith('no_compatible')


def test_chunk_provenance_and_overlap():
    doc=Document(id='long',title='Long manual',source='curated://long',revision='1',component='mysql',content='\n'.join(f'{i}: '+ 'x'*180 for i in range(20)))
    refs=list(chunks(doc))
    assert len(refs)>1 and refs[1]['start']==refs[0]['end']
    assert refs[0]['text']=='\n'.join(doc.content.splitlines()[refs[0]['start']-1:refs[0]['end']])
    assert len({r['sha256'] for r in refs})==1
    assert bm25('missingword',['hello'])==[0]


async def test_embedding_http_contract(settings,monkeypatch):
    settings.embedding_base_url='http://localhost:9999/v1';settings.embedding_model='fixture'
    original=httpx.AsyncClient
    def handler(request):
        assert request.url.path=='/v1/embeddings'
        data=json.loads(request.content)
        return httpx.Response(200,json={'data':[{'index':i,'embedding':[float(i+1),1.]} for i in reversed(range(len(data['input'])))]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    assert await Embeddings(settings).encode(['a','b'])==[[1.,1.],[2.,1.]]


@pytest.mark.parametrize('url',['http://localhost.evil/v1','https://user:password@example.com/v1'])
def test_embedding_endpoint_validation(settings,url):
    settings.embedding_base_url=url;settings.embedding_model='fixture'
    with pytest.raises(ValueError): Embeddings(settings)


@pytest.mark.parametrize('vector',[[],[0.,0.],[float('nan'),1.],[float('inf'),1.],[True,1.],['bad',1.]])
def test_invalid_embedding_vectors(vector):
    with pytest.raises(ValueError): vector_checked(vector)


def test_context_keeps_knowledge_handles():
    from devtriage.context import compact
    kid='kb-'+'a'*24
    messages=[{'role':'system','content':'goal'},{'role':'user','content':'task'},
              {'role':'tool','content':json.dumps({'id':kid,'text':'x'*5000})}]+[{'role':'user','content':'recent'}]*4
    assert kid in compact(messages,2000)[2]['content']


async def test_agent_knowledge_reference_is_not_incident_evidence(settings,source,tmp_path):
    await ingest(settings,source)
    repo=tmp_path/'repo';repo.mkdir();(repo/'Service.java').write_text('class Service {}')
    log=tmp_path/'a.log';log.write_text('java.lang.RuntimeException: fail\n at Service.go(Service.java:1)')
    class Provider:
        step=0
        async def complete(self,messages,tools):
            self.step+=1
            if self.step==1:
                assert any(t['function']['name']=='search_knowledge' for t in tools)
                return {'role':'assistant','tool_calls':[{'id':'k','type':'function','function':{'name':'search_knowledge','arguments':'{"query":"Hikari"}'}}]},{}
            ref=json.loads(messages[-1]['content'])['data']['matches'][0]['reference']
            return {'role':'assistant','content':json.dumps({'symptom':'异常','root_cause':'历史案例待核实','knowledge_ids':[ref['id']], 'knowledge':[dict(ref,text='fabricated')], 'status':'insufficient'})},{}
    report=await diagnose(DiagnosisRequest(repo=str(repo),log=str(log)),settings,Provider())
    assert report.status=='insufficient' and not report.evidence
    assert report.knowledge[0].text!='fabricated'
    saved=(settings.data_dir/report.run_id/'report.md').read_text(encoding='utf-8')
    assert 'curated://pool' in saved and 'private-value' not in saved


async def test_knowledge_cannot_support_diagnosis_alone(settings,source,tmp_path):
    await ingest(settings,source)
    repo=tmp_path/'repo';repo.mkdir();log=tmp_path/'incident.log'
    log.write_text('java.lang.RuntimeException: fail')
    class Provider:
        step=0
        async def complete(self,messages,tools):
            self.step+=1
            if self.step==1:
                return {'role':'assistant','tool_calls':[{'id':'k','type':'function','function':{'name':'search_knowledge','arguments':'{"query":"Hikari"}'}}]},{}
            if self.step==2:
                ref=json.loads(messages[-1]['content'])['data']['matches'][0]['reference']
                self.kid=ref['id']
                return {'role':'assistant','content':json.dumps({'symptom':'异常','root_cause':'历史案例','knowledge_ids':[self.kid],'status':'supported'})},{}
            assert 'log AND source' in messages[-1]['content']
            return {'role':'assistant','content':json.dumps({'symptom':'异常','root_cause':'证据不足','knowledge_ids':[self.kid],'status':'insufficient'})},{}
    report=await diagnose(DiagnosisRequest(repo=str(repo),log=str(log)),settings,Provider())
    assert report.status=='insufficient' and report.knowledge


async def test_retrieval_evaluation(settings):
    from devtriage.rag_evaluation import evaluate_retrieval
    await ingest(settings,PROJECT/'knowledge/runbooks.json')
    report=await evaluate_retrieval(settings,PROJECT/'evals/retrieval.json')
    assert report['modes']['keyword']['averages']['recall_at_5']==1
    assert report['modes']['keyword']['averages']['abstention']==1
    assert not report['modes']['hybrid']['fully_available']


@pytest.mark.skipif(not os.getenv('DEVTRIAGE_TEST_RAG_DSN'),reason='requires dedicated pgvector database')
async def test_real_pgvector(settings,source):
    settings.rag_backend='postgres'
    from pydantic import SecretStr
    settings.rag_dsn=SecretStr(os.environ['DEVTRIAGE_TEST_RAG_DSN'])
    embedder=FakeEmbeddings()
    await ingest(settings,source,corpus='test',embedder=embedder)
    search=KnowledgeSearch(settings,'global',embedder)
    result=await search.search(KnowledgeArgs(query='数据库等待',mode='dense'))
    assert result['matches'][0]['reference']['document_id']=='pool'
    assert result['matches'][0]['cosine_similarity']==pytest.approx(1.)
    store=KnowledgeStore(settings)
    try: store.replace('test',[],embedder.fingerprint)
    finally: store.close()
