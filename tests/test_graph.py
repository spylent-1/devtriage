import json
from devtriage.agent import diagnose
from devtriage.config import Settings
from devtriage.models import DiagnosisRequest
from devtriage.store import Store


def call(name, args, call_id):
    return {'id': call_id, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}


async def test_graph_multiple_tools_and_report_correction(tmp_path):
    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'Service.java').write_text('class Service {}', encoding='utf8')
    log = tmp_path / 'incident.log'; log.write_text('java.lang.Exception: failed', encoding='utf8')
    class Provider:
        def __init__(self): self.steps = 0
        async def complete(self, messages, tools):
            self.steps += 1
            if self.steps == 1:
                return {'role':'assistant', 'tool_calls':[call('read_file', {'path':'Service.java'}, '1'), call('parse_java_log', {}, '2')]}, {}
            if self.steps == 2:
                assert [m['tool_call_id'] for m in messages[-2:]] == ['1', '2']
                return {'role':'assistant', 'content':json.dumps({'symptom':'x','root_cause':'y','status':'reproduced','evidence_ids':['fake']})}, {}
            assert 'Invalid final report' in messages[-1]['content']
            return {'role':'assistant', 'content':json.dumps({'symptom':'x','root_cause':'unknown','status':'insufficient'})}, {}
    provider = Provider()
    settings = Settings(data_dir=tmp_path/'state', max_rounds=3, rag_enabled=False)
    report = await diagnose(DiagnosisRequest(repo=str(repo), log=str(log)), settings, provider)
    assert provider.steps == 3
    assert report.status == 'insufficient'
    store = Store(settings.data_dir)
    assert store.report(report.run_id)['state'] == 'completed'
    store.db.close()


async def test_graph_tool_failure_is_observed(tmp_path):
    repo = tmp_path / 'repo'; repo.mkdir()
    log = tmp_path / 'incident.log'; log.write_text('INFO', encoding='utf8')
    class Provider:
        async def complete(self, messages, tools):
            if messages[-1]['role'] != 'tool':
                return {'role':'assistant', 'tool_calls':[call('read_file', {'path':'.env'}, '1')]}, {}
            assert json.loads(messages[-1]['content'])['ok'] is False
            return {'role':'assistant', 'content':json.dumps({'symptom':'x','root_cause':'unknown','status':'insufficient'})}, {}
    report = await diagnose(DiagnosisRequest(repo=str(repo), log=str(log)), Settings(data_dir=tmp_path/'state', rag_enabled=False), Provider())
    assert report.status == 'insufficient'
