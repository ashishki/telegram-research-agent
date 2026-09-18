"""Offline bridge tests; no credentials, models or network."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / 'tools/playbook.py'
spec = importlib.util.spec_from_file_location('pinned_playbook_bridge', MODULE_PATH)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
PIN = 'd570163ab17ec3b4245187c778f1e8d89af9690f'
URL = 'https://github.com/ashishki/AI_workflow_playbook.git'


def fixture(tmp_path):
    upstream = tmp_path / '.playbook/upstream'
    upstream.mkdir(parents=True)
    (upstream / '.git').write_text('gitdir: ignored-by-mock\n')
    (tmp_path / '.playbook/upstream.lock.json').write_text(json.dumps({
        'path': '.playbook/upstream', 'commit': PIN, 'repository': URL,
    }))
    def git(root, *args):
        return {
            ('rev-parse', '--show-toplevel'): str(upstream),
            ('rev-parse', 'HEAD'): PIN,
            ('ls-files', '--stage', '--', '.playbook/upstream'): '160000 ' + PIN + ' 0\t.playbook/upstream',
            ('config', '--file', '.gitmodules', '--get', 'submodule.ai-workflow-playbook.url'): URL,
            ('status', '--porcelain', '--untracked-files=all'): '',
        }[args]
    return upstream, git


def test_verified_pin(tmp_path):
    upstream, git = fixture(tmp_path)
    with patch.object(bridge, 'git', side_effect=git):
        assert bridge.verified_upstream(tmp_path) == upstream


def test_dirty_pin_fails_closed(tmp_path):
    _, git = fixture(tmp_path)
    def changed(root, *args):
        return ' M tools/feature_workflow.py' if args[0] == 'status' else git(root, *args)
    with patch.object(bridge, 'ROOT', tmp_path), patch.object(bridge, 'git', side_effect=changed):
        assert bridge.main(['--check-pin']) == 2


def test_wrong_commit_fails_closed(tmp_path):
    _, git = fixture(tmp_path)
    def changed(root, *args):
        return '0' * 40 if args == ('rev-parse', 'HEAD') else git(root, *args)
    with patch.object(bridge, 'ROOT', tmp_path), patch.object(bridge, 'git', side_effect=changed):
        assert bridge.main(['--check-pin']) == 2


def test_missing_submodule_and_unknown_tool_do_not_execute(tmp_path):
    with patch.object(bridge, 'ROOT', tmp_path), patch.object(bridge.subprocess, 'run') as run:
        assert bridge.main(['--check-pin']) == 2
        assert bridge.main(['../../dangerous']) == 2
        run.assert_not_called()


def test_symlink_rejected(tmp_path):
    upstream, _ = fixture(tmp_path)
    (upstream / '.git').unlink()
    upstream.rmdir()
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    upstream.symlink_to(elsewhere, target_is_directory=True)
    with patch.object(bridge, 'ROOT', tmp_path):
        assert bridge.main(['--check-pin']) == 2


def test_forwarding_preserves_arguments_and_exit_code(tmp_path):
    upstream, _ = fixture(tmp_path)
    (upstream / 'tools').mkdir()
    (upstream / 'tools/feature_workflow.py').write_text('# inert fixture\n')
    with patch.object(bridge, 'ROOT', tmp_path), patch.object(bridge, 'verified_upstream', return_value=upstream), patch.object(bridge.subprocess, 'run') as run:
        run.return_value.returncode = 17
        assert bridge.main(['feature_workflow', '--root', '.', 'plan', '--task', 'PA-00']) == 17
        assert run.call_args.args[0] == [bridge.sys.executable, str(upstream / 'tools/feature_workflow.py'), '--root', '.', 'plan', '--task', 'PA-00']
        assert 'shell' not in run.call_args.kwargs
