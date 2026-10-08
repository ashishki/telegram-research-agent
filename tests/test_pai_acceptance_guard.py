from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pai_acceptance', ROOT / 'tools/run_pai_acceptance.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_real_pytest_skip_is_failure_and_passing_case_is_accepted(tmp_path):
    test = tmp_path / 'test_synthetic_acceptance.py'
    test.write_text('import pytest\ndef test_synthetic(): pytest.skip("synthetic unsupported dependency")\n')
    env = {**os.environ, 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}
    result = subprocess.run([sys.executable, str(ROOT / 'tools/run_pai_acceptance.py'), '-q', str(test)], env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert 'skipped, failed or errored' in result.stdout
    test.write_text('def test_synthetic(): assert 2 + 2 == 4\n')
    result = subprocess.run([sys.executable, str(ROOT / 'tools/run_pai_acceptance.py'), '-q', str(test)], env=env, capture_output=True, text=True)
    assert result.returncode == 0
    assert '1 acceptance cases, zero skips/failures' in result.stdout


def test_missing_zero_or_omitted_matrix_cases_fail(tmp_path):
    report = tmp_path / 'report.xml'
    assert guard.verify_report(report)[0] is False
    report.write_text('<testsuites/>')
    assert guard.verify_report(report)[0] is False
    matrix = {'requirements': [{'spec_id': 'CHAT-01', 'case_name': 'test_requirement_chat_01'}],
              'scenarios': [{'scenario_id': 'SC13.2-01', 'synthetic_test_node': 'tests/test_pai_end_to_end.py::test_chat'}]}
    root = ET.Element('testsuite')
    ET.SubElement(root, 'testcase', classname='tests.test_pai_end_to_end', name='test_chat')
    ET.ElementTree(root).write(report)
    assert guard.verify_report(report, matrix=matrix)[0] is False
    ET.SubElement(root, 'testcase', classname='tests.test_pai_requirements', name='test_requirement_chat_01')
    ET.ElementTree(root).write(report)
    assert guard.verify_report(report, matrix=matrix)[0] is True


def test_duplicate_or_wrong_module_cannot_substitute_required_acceptance(tmp_path):
    report=tmp_path/'report.xml'
    matrix={'requirements':[{'spec_id':'CHAT-01','case_name':'test_requirement_chat_01'}],'scenarios':[]}
    report.write_text('<testsuite><testcase classname="tests.other" name="test_requirement_chat_01"/></testsuite>')
    assert guard.verify_report(report,matrix=matrix)[0] is False
    report.write_text('<testsuite>'+2*'<testcase classname="tests.test_pai_requirements" name="test_requirement_chat_01"/>'+'</testsuite>')
    assert guard.verify_report(report,matrix=matrix)==(False,'duplicate acceptance test nodes')


def test_no_implicit_historical_suite_or_filter_bypass():
    for args in (['-q'], ['tests'], ['-k', 'one_case', 'tests/test_pai_plan.py'],
                 ['--junitxml=other.xml', 'tests/test_pai_plan.py']):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/run_pai_acceptance.py'), *args], capture_output=True, text=True)
        assert result.returncode == 2
        assert 'usage:' in result.stderr


def test_malformed_and_parameterized_scenario_nodes_have_explicit_results(tmp_path):
    report=tmp_path/'report.xml'
    report.write_text('<testsuite><testcase classname="tests.test_pai_end_to_end" name="test_chat[param]"/></testsuite>')
    row={'scenario_id':'SC13.2-01','synthetic_test_node':'tests/test_pai_end_to_end.py::test_chat[param]'}
    matrix={'requirements':[],'scenarios':[row]}
    assert guard.verify_report(report,matrix=matrix)[0] is True
    for node in ('tests/test_pai_end_to_end.py::Class::test_chat','malformed','tests/test_pai_end_to_end.py::'):
        row['synthetic_test_node']=node
        assert guard.verify_report(report,matrix=matrix)==(False,'invalid binding test node')
