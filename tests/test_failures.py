import json
from contextlib import contextmanager
from pathlib import Path
import pytest
from devtriage.agent import diagnose
from devtriage.config import Settings
from devtriage.models import DiagnosisRequest
from devtriage.tools import Repository, ToolRegistry
from devtriage.store import Store
from devtriage.process import run


@pytest.fixture
def incident(tmp_path):
    repo=tmp_path/'repo'; repo.mkdir()
    (repo/'Service.java').write_text('class Service {}')
    log=tmp_path/'incident.log'; log.write_text('java.lang.Exception: failed')
    return repo, log


class Repeat:
    async def complete(self, messages, tools):
        return {'role':'assistant','tool_calls':[{'id':str(len(messages)), 'type':'function',
          'function':{'name':'read_file','arguments':'{"path":"Service.java"}'}}]}, {}


async def test_repeated_tools_stop(incident, tmp_path):
    repo,log=incident
    report=await diagnose(DiagnosisRequest(repo=str(repo),log=str(log)),Settings(data_dir=tmp_path/'state'),Repeat())
    assert report.status=='insufficient'
    assert 'Repeated identical' in report.gaps[0]


class Interrupt:
    async def complete(self, messages, tools):
        import asyncio
        raise asyncio.CancelledError()


async def test_interrupted_persisted(incident,tmp_path):
    repo,log=incident
    settings=Settings(data_dir=tmp_path/'state')
    report=await diagnose(DiagnosisRequest(repo=str(repo),log=str(log)),settings,Interrupt())
    assert Store(settings.data_dir).report(report.run_id)['state']=='interrupted'


async def test_no_read_evaluation_or_tests(incident):
    repo,log=incident
    (repo/'src/test').mkdir(parents=True)
    (repo/'src/test/Answer.java').write_text('answer')
    tools=ToolRegistry(Repository(repo,log))
    assert not (await tools.execute('read_file',{'path':'src/test/Answer.java'})).ok
    assert not (await tools.execute('read_file',{'path':'Service.java','start':2})).ok


class Fabricate:
    async def complete(self,messages,tools):
        return {'role':'assistant','content':json.dumps({'symptom':'x','root_cause':'y','status':'reproduced','evidence_ids':['fake']})},{}


async def test_invented_evidence_rejected(incident,tmp_path):
    repo,log=incident
    result=await diagnose(DiagnosisRequest(repo=str(repo),log=str(log)),Settings(data_dir=tmp_path/'state',max_rounds=2),Fabricate())
    assert result.status=='insufficient'
    assert not result.evidence


async def test_subprocess_timeout():
    import sys
    with pytest.raises(TimeoutError):
        await run([sys.executable,'-c','import time; time.sleep(10)'],timeout=0.1)


def test_context_exceeds_budget():
    from devtriage.context import compact
    with pytest.raises(ValueError):
        compact([{'role':'system','content':'x'*1000}],100)


async def test_telemetry_failure_isolated(incident,tmp_path,monkeypatch):
    from devtriage.telemetry import Telemetry
    class Broken:
        def start_as_current_observation(self,**kwargs): raise RuntimeError('offline')
        def flush(self): raise RuntimeError('offline')
    telemetry=Telemetry(); telemetry.client=Broken()
    repo,log=incident
    report=await diagnose(DiagnosisRequest(repo=str(repo),log=str(log)),Settings(data_dir=tmp_path/'state',max_rounds=1),Fabricate(),telemetry)
    assert report.run_id
    assert (tmp_path/'state'/report.run_id/'report.json').exists()
