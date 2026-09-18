"""Offline bridge tests; no credentials, models or network."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
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


def test_verifier_literal_is_loaded_without_running_initializer(tmp_path):
    upstream, _ = fixture(tmp_path)
    (upstream / 'tools').mkdir()
    marker = tmp_path / 'installer-ran'
    code = 'def main():\n    return 23\n'
    source = 'from pathlib import Path\n' + f'Path({str(marker)!r}).write_text("bad")\n'
    source += 'def verify_project_script():\n    return ' + repr(code) + '\n'
    (upstream / 'tools/init_playbook_project.py').write_text(source)
    assert bridge.load_generated_verifier(upstream).main() == 23
    assert not marker.exists()


def test_verifier_nonliteral_generation_fails_closed(tmp_path):
    upstream, _ = fixture(tmp_path)
    (upstream / 'tools').mkdir()
    (upstream / 'tools/init_playbook_project.py').write_text(
        'def verify_project_script():\n    return generate_unreviewed_code()\n'
    )
    with patch.object(bridge, 'ROOT', tmp_path), patch.object(bridge, 'verified_upstream', return_value=upstream):
        assert bridge.main(['verify_project']) == 2


def test_verifier_template_symlink_fails_closed(tmp_path):
    upstream, _ = fixture(tmp_path)
    (upstream / 'tools').mkdir()
    outside = tmp_path / 'outside.py'
    outside.write_text('def verify_project_script():\n    return "def main(): return 0"\n')
    (upstream / 'tools/init_playbook_project.py').symlink_to(outside)
    with patch.object(bridge, 'ROOT', tmp_path), patch.object(bridge, 'verified_upstream', return_value=upstream):
        assert bridge.main(['verify_project']) == 2


def test_generated_verifier_receives_exact_args_and_restores_argv(tmp_path):
    upstream, _ = fixture(tmp_path)
    (upstream / 'tools').mkdir()
    code = 'import sys\ndef main():\n    return 29 if sys.argv[1:] == ["--root", "."] else 1\n'
    (upstream / 'tools/init_playbook_project.py').write_text(
        'def verify_project_script():\n    return ' + repr(code) + '\n'
    )
    previous = bridge.sys.argv
    with patch.object(bridge, 'ROOT', tmp_path), patch.object(bridge, 'verified_upstream', return_value=upstream):
        assert bridge.main(['verify_project', '--root', '.']) == 29
    assert bridge.sys.argv is previous


def test_renderer_entrypoint_uses_pinned_role_set():
    result = subprocess.run(
        [sys.executable, str(ROOT / 'tools/render_codex_exec_prompt.py'), '--help'],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert 'product_design_review' in result.stdout
    assert 'program_design_review' in result.stdout
