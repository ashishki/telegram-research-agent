"""Explicit startup and pure config checking, with no ambient effects."""
from dataclasses import asdict
import json
from types import SimpleNamespace

import pytest

from prm import cli
from prm.briefs import brief_owner_ref_from_authenticated_private_tuple
from prm.runtime.config import check_runtime_configuration
from tests.pai_runtime_fixtures import pai


def configuration():
    return {'owner_ref': brief_owner_ref_from_authenticated_private_tuple('42', '42', '42'),
            'owner_chat_id': '42', 'budget_refs': ['request_daily', 'day_daily', 'month_daily'],
            'job_budget': False, 'local_services': True}


def target_configuration():
    return dict(backend='postgresql', host='127.0.0.1', port=15432,
                database='pa_test_daily', user='pa_test_app', instance_id='a' * 32, target='synthetic-test')


@pytest.mark.parametrize('patch', [{}, {'unexpected': 'private_marker'}, {'job_budget': 'yes'},
                                  {'owner_chat_id': '43'}, {'budget_refs': []},
                                  {'model': {'token': 'private_marker'}}, {'local_services': 'yes'}])
def test_invalid_config_never_reports_ready_or_secrets(patch):
    config = {} if not patch else {**configuration(), **patch}
    result = check_runtime_configuration(mode='durable', config=config, target=target_configuration())
    assert not result.valid
    assert 'private_marker' not in json.dumps(asdict(result))
    assert result.observed_runtime == 'unknown'


def test_offline_check_cli_and_help_do_not_load_settings_connect_or_start(tmp_path, monkeypatch, capsys):
    from prm.storage.postgres import SyntheticTarget
    def forbidden(*args, **kwargs):
        pytest.fail('offline command attempted an effect')
    monkeypatch.setattr(cli, 'load_settings', forbidden)
    monkeypatch.setattr(cli, 'run_bot', forbidden)
    monkeypatch.setattr(SyntheticTarget, 'connect', forbidden)
    config, target = tmp_path / 'runtime.json', tmp_path / 'target.json'
    config.write_text(json.dumps(configuration()))
    target.write_text(json.dumps(target_configuration()))
    assert cli.main(['runtime-check', '--runtime-config', str(config), '--synthetic-target', str(target)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary['selected_mode'] == 'durable' and summary['observed_runtime'] == 'unknown'
    assert 'weekly' in summary['configured_capabilities']
    with pytest.raises(SystemExit) as help_exit:
        cli.main(['--help'])
    assert help_exit.value.code == 0


def test_missing_durable_config_is_rejected_before_loading_settings(monkeypatch, capsys):
    monkeypatch.setattr(cli, 'load_settings', lambda: pytest.fail('settings loaded before preflight'))
    assert cli.main(['assistant']) == 2
    assert 'runtime_config' in capsys.readouterr().out


def test_explicit_compatibility_uses_old_entrypoint(monkeypatch):
    observed = []
    monkeypatch.setattr(cli, 'load_settings', lambda: SimpleNamespace(db_path=':memory:'))
    monkeypatch.setattr(cli, 'run_bot', lambda *args, **kwargs: observed.append(kwargs))
    assert cli.main(['assistant', '--mode', 'compatibility']) == 0
    assert 'job_ingress' not in observed[0]


def test_compatibility_refuses_durable_arguments(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'load_settings', lambda: pytest.fail('invalid startup loaded settings'))
    assert cli.main(['assistant', '--mode', 'compatibility', '--runtime-config', str(tmp_path / 'missing')]) == 2


def test_malformed_config_error_is_redacted(tmp_path, capsys):
    config = tmp_path / 'bad.json'
    config.write_text('{"token": "private_marker", broken}')
    assert cli.main(['runtime-check', '--runtime-config', str(config)]) == 2
    assert 'private_marker' not in capsys.readouterr().out


def test_complete_durable_cli_composes_one_root(pai, tmp_path, monkeypatch):
    observed = []
    config, target = tmp_path / 'runtime.json', tmp_path / 'target.json'
    config.write_text(json.dumps(configuration()))
    target.write_text(json.dumps(asdict(pai.pg.app)))
    monkeypatch.setattr(cli, 'load_settings', lambda: SimpleNamespace(db_path=':memory:'))
    monkeypatch.setattr(cli, 'run_bot', lambda *args, **kwargs: observed.append(kwargs))
    assert cli.main(['assistant', '--mode', 'durable', '--runtime-config', str(config),
                     '--synthetic-target', str(target), '--owner-ref', configuration()['owner_ref'], '--owner-chat-id', '42']) == 0
    assert observed[0]['job_ingress'].durable_results
