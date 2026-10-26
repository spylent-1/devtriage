import asyncio
import json
from pathlib import Path
import pytest
from devtriage.tools import Repository, ToolRegistry
from devtriage.logs import parse_log
from devtriage.context import compact
from devtriage.models import DiagnosisRequest
from devtriage.config import Settings, LAB, PROJECT
from devtriage.agent import diagnose
from devtriage.store import Store
from devtriage.lab import validate_xml
from devtriage.redaction import redact


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "Service.java").write_text('class Service {\n  String checkout() { return null; }\n}\n')
    log = tmp_path / "incident.log"
    log.write_text('java.lang.NullPointerException: missing\n\tat Service.checkout(Service.java:2)\n')
    return Repository(root, log)


def test_log_nested():
    result = parse_log('java.lang.RuntimeException: top\nCaused by: java.sql.SQLException: down\n\tat app.Service.go(Service.java:7)\nrequestId=abc-42')
    assert len(result['exceptions']) == 2
    assert result['frames'][0]['line'] == 7
    assert result['correlation_ids'] == ['abc-42']
    assert parse_log('INFO good')['exceptions'] == []


@pytest.mark.parametrize('path', ['../incident.log', '.env', 'src/test/Answer.java', 'evals/answer.txt'])
def test_boundary(repo, path):
    with pytest.raises((ValueError, FileNotFoundError)):
        repo.path(path)


def test_stale_evidence(repo):
    ref = repo.read(repo.path('Service.java'), 1, 2)
    assert repo.validate([ref['id']])[0].text.startswith('class')
    with pytest.raises(ValueError):
        repo.validate(['invented'])
    repo.path('Service.java').write_text('changed')
    with pytest.raises(ValueError, match='Stale'):
        repo.validate([ref['id']])


async def test_tools(repo):
    tools = ToolRegistry(repo)
    assert not (await tools.execute('read_file', {'path':'Service.java','start':0})).ok
    assert not (await tools.execute('run_lab_test', {'case_id':'case-1'})).ok
    assert not (await tools.execute('shell', {'command':'whoami'})).ok
    assert (await tools.execute('inspect_java_symbol', {'path':'Service.java','symbol':'checkout'})).data['symbols'][0]['start'] == 2
    assert (await tools.execute('search_code', {'query':'checkout'})).data['matches']


def test_context():
    messages = [{'role':'system','content':'goal'},{'role':'user','content':'task'},
                {'role':'tool','content':'x'*10000}] + [{'role':'user','content':'recent'}]*4
    result = compact(messages, 2000)
    assert result[0]['content'] == 'goal'
    assert 'omitted' in result[2]['content']
    assert len(messages[2]['content']) == 10000


class FakeProvider:
    def __init__(self, fail=False): self.step=0; self.fail=fail
    async def complete(self, messages, tools):
        if self.fail: raise TimeoutError('model timeout')
        self.step += 1
        if self.step == 1:
            return {'role':'assistant','tool_calls':[{'id':'1','type':'function','function':{'name':'read_file','arguments':json.dumps({'path':'Service.java','start':1,'end':3})}}]}, {}
        tool = json.loads(messages[-1]['content'])['data']
        initial = json.loads(messages[1]['content'].split('Initial log summary (untrusted):\n')[1])
        report = {'symptom':'异常','root_cause':'返回空值','status':'supported',
                  'evidence_ids':[tool['id'], initial['data']['evidence']['id']]}
        return {'role':'assistant','content':json.dumps(report)}, {'prompt_tokens':10,'completion_tokens':10}


async def test_agent_and_store(repo, tmp_path):
    settings = Settings(data_dir=tmp_path/'state')
    report = await diagnose(DiagnosisRequest(repo=str(repo.root),log=str(repo.log)), settings, FakeProvider())
    assert report.status == 'supported'
    assert len(report.evidence) == 2
    store = Store(settings.data_dir)
    assert store.report(report.run_id)['state'] == 'completed'
    assert (settings.data_dir/report.run_id/'report.md').exists()


async def test_model_failure(repo, tmp_path):
    settings = Settings(data_dir=tmp_path/'state')
    report = await diagnose(DiagnosisRequest(repo=str(repo.root),log=str(repo.log)), settings, FakeProvider(True))
    assert report.status == 'insufficient'
    assert Store(settings.data_dir).report(report.run_id)['state'] == 'failed'


async def test_round_limit(repo, tmp_path):
    settings = Settings(data_dir=tmp_path/'state',max_rounds=1)
    report = await diagnose(DiagnosisRequest(repo=str(repo.root),log=str(repo.log)), settings, FakeProvider())
    assert 'Maximum rounds' in report.gaps[0]


def test_xml_requires_assertions_and_control():
    assert validate_xml('<testsuite><testcase name="scenario1"><system-out>java.lang.NullPointerException at dev.triage.lab.OrderService.checkout(OrderService.java:25)</system-out></testcase><testcase name="control1"/></testsuite>', 'case-1') == (True,True)
    assert validate_xml('<testsuite><testcase name="scenario1"><failure/></testcase></testsuite>', 'case-1') == (False,False)


def test_redact():
    result = redact('password=abc api_key=xyz Authorization: Bearer token jdbc:mysql://u:p@host')
    assert 'abc' not in result and 'xyz' not in result and 'Bearer token' not in result and ':p@' not in result


def test_dataset_and_compose():
    import yaml
    rows=json.loads((PROJECT/'evals/baseline.json').read_text())
    assert len(rows)==12
    assert all((PROJECT/r['log']).exists() for r in rows)
    compose=yaml.safe_load((PROJECT/'lab/compose.yaml').read_text())
    assert set(compose['services']) == {'mysql','redis','app','tests'}
    assert compose['services']['tests']['volumes'][0].endswith(':ro')


@pytest.mark.skipif(not __import__('os').getenv('DEVTRIAGE_LAB_INTEGRATION'), reason='requires running Docker lab')
@pytest.mark.parametrize('case_id',['case-1','case-2','case-3'])
async def test_live_lab(case_id):
    from devtriage.lab import verify_case
    result = await verify_case(case_id)
    assert result.reproduced and result.healthy_control
