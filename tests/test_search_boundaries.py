import json

import pytest

from devtriage.tools import Repository, ToolRegistry


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    log = tmp_path / 'incident.log'
    log.write_text('java.lang.RuntimeException: failure')
    return Repository(root, log)


async def test_search_excludes_protected_nested_directories(repository):
    paths = ['src/main/java/Service.java', 'module/src/main/java/Service.java',
             'tests/Answer.java', 'module/src/test/java/Answer.java',
             'module/tests/Answer.java', 'module/target/Generated.java',
             'evals/Answer.java', 'module/Tests/Answer.java']
    for name in paths:
        path = repository.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('class Service { String probe = "ProbeMarker"; }')
    registry = ToolRegistry(repository)
    result = await registry.execute('search_code', {'query': 'ProbeMarker'})
    assert result.ok
    assert {hit['path'] for hit in result.data['matches']} == set(paths[:2])
    for path in paths[2:]:
        assert not (await registry.execute('read_file', {'path': path})).ok


async def test_search_keeps_valid_hits_when_other_matches_are_unusable(repository, monkeypatch):
    import devtriage.tools as module

    (repository.root / 'Service.java').write_text('class Service {}')
    (repository.root / 'Unreadable.java').write_text('class Hidden {}')
    original_read = repository.read

    def read(path, *args, **kwargs):
        if path.name == 'Unreadable.java':
            raise PermissionError('fixture')
        return original_read(path, *args, **kwargs)

    async def run(*args, **kwargs):
        return {'returncode': 0, 'output': '\n'.join(json.dumps({
            'type': 'match', 'data': {'path': {'text': path}, 'line_number': 1}
        }) for path in ['../incident.log', 'Missing.java', 'Unreadable.java', 'Service.java'])}

    monkeypatch.setattr(module, 'run', run)
    monkeypatch.setattr(repository, 'read', read)
    result = await ToolRegistry(repository).execute('search_code', {'query': 'class'})
    assert result.ok and [hit['path'] for hit in result.data['matches']] == ['Service.java']
    for path in ['../incident.log', 'Missing.java']:
        assert not (await ToolRegistry(repository).execute('read_file', {'path': path})).ok


async def test_search_process_failure_is_not_hidden(repository, monkeypatch):
    import devtriage.tools as module

    async def run(*args, **kwargs):
        return {'returncode': 2, 'output': 'fatal search error'}

    monkeypatch.setattr(module, 'run', run)
    result = await ToolRegistry(repository).execute('search_code', {'query': 'class'})
    assert not result.ok and 'ripgrep failed' in result.error
