import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from devtriage.tools import ToolRegistry, Repository, SearchArgs
from devtriage.evaluation import evaluate
from devtriage.models import DiagnosisReport
from devtriage.config import Settings, PROJECT
from devtriage.redaction import redact_data


async def test_dynamic_registry(tmp_path):
    log=tmp_path/'a.log'; log.write_text('INFO')
    registry=ToolRegistry(Repository(tmp_path,log))
    async def handler(args): return {'query':args.query}
    registry.register('custom_search',SearchArgs,'Trusted extension',handler)
    result=await registry.execute('custom_search',{'query':'example'})
    assert result.ok and result.data['query']=='example'
    with pytest.raises(ValueError):
        registry.register('custom_search',SearchArgs,'duplicate',handler)


def test_structured_redaction_preserves_json():
    source={'text':'password="abc"\nsecret=xyz', 'api_key':'sk-real-key', 'nested':[{'value':'正常文本'}]}
    result=json.loads(json.dumps(redact_data(source),ensure_ascii=False))
    assert 'abc' not in result['text'] and 'xyz' not in result['text']
    assert result['api_key']=='[REDACTED]'
    assert result['nested'][0]['value']=='正常文本'


async def test_cloud_sdk_async_contract(tmp_path,monkeypatch):
    import asyncio
    import devtriage.evaluation as module
    import devtriage.telemetry as telemetry_module
    rows=json.loads((PROJECT/'evals/baseline.json').read_text())
    async def fake_diagnose(request,settings):
        run_id=Path(request.log).stem
        folder=settings.data_dir/run_id; folder.mkdir(parents=True,exist_ok=True)
        report=DiagnosisReport(run_id=run_id,symptom='test',root_cause='unknown')
        (folder/'report.json').write_text(report.model_dump_json(),encoding='utf8')
        return report
    class Dataset:
        def run_experiment(self,**kwargs):
            async def execute():
                for row in rows:
                    output=await kwargs['task'](item=SimpleNamespace(input={'id':row['id']}))
                    assert kwargs['evaluators'][0](output=output)
            asyncio.run(execute())
    class Client:
        def create_dataset(self,**kwargs): pass
        def create_dataset_item(self,**kwargs): pass
        def get_dataset(self,name): return Dataset()
    class Telemetry:
        client=Client()
        def flush(self): pass
    monkeypatch.setattr(module,'diagnose',fake_diagnose)
    monkeypatch.setattr(telemetry_module,'Telemetry',Telemetry)
    monkeypatch.setattr(module,'Telemetry',Telemetry)
    settings=Settings(data_dir=tmp_path/'state')
    result=await evaluate(settings,cloud=True)
    assert len(result['items'])==12
    assert result['averages']['verification'] is None
