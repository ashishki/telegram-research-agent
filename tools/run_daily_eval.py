#!/usr/bin/env python3
"""Run or verify the frozen native synthetic tasks. No keys/live provider route."""
from pathlib import Path
import argparse
import json
import re
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from prm.runtime.evaluation import load_daily_manifest,_daily_json,daily_digest,verify_daily_trace_suite
from prm.storage.postgres import StorageError


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=ROOT/'evals/assistant_judge/daily_tasks.v1.json')
    parser.add_argument('--verify',type=Path,help='offline verification only, no fixture starts')
    parser.add_argument('--output',type=Path,help='create a new public synthetic trace packet; no overwrite')
    args=parser.parse_args(argv)
    if args.verify and args.output:parser.error('verify and output are separate operations')
    try:
        manifest=load_daily_manifest(args.manifest)
        if args.verify:
            packet=_daily_json(args.verify)
            if not isinstance(packet,dict) or set(packet)!={'schema_version','manifest_digest','source_sha','working_diff_sha256','traces','summary'} or packet['schema_version']!='assistant.daily_trace_packet.v1' or packet['manifest_digest']!=daily_digest(manifest):
                raise StorageError('complete bound daily trace packet required')
            if not isinstance(packet['source_sha'],str) or not re.fullmatch('[a-f0-9]{40}',packet['source_sha']) or not isinstance(packet['working_diff_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',packet['working_diff_sha256']):
                raise StorageError('exact source SHA and working diff hash required')
            summary=verify_daily_trace_suite(manifest,packet['traces'])
            if summary!=packet['summary']:raise StorageError('trace packet summary changed')
        else:
            paths=['src','tests','tools','evals']
            if subprocess.run(['git','diff','--quiet','HEAD','--',*paths],cwd=ROOT).returncode:
                raise StorageError('freeze implementation source before native capture')
            untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard','--',*paths],cwd=ROOT)
            if untracked:raise StorageError('untracked implementation source cannot claim a frozen capture')
            from tests.pai_runtime_fixtures import pai
            from tests.daily_eval_fixtures import run_daily_fixture
            import hashlib
            source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
            diff=subprocess.check_output(['git','diff','--binary','HEAD','--',*paths],cwd=ROOT)
            traces=[]
            with tempfile.TemporaryDirectory(prefix='daily-native-eval-') as directory:
                for case in manifest['cases']:
                    case_dir=Path(directory)/case['case_id'];case_dir.mkdir()
                    fixture=pai.__wrapped__(case_dir)
                    try:traces.append(run_daily_fixture(case,next(fixture),manifest))
                    finally:fixture.close()
            if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=source_sha or subprocess.run(['git','diff','--quiet','HEAD','--',*paths],cwd=ROOT).returncode or subprocess.check_output(['git','ls-files','--others','--exclude-standard','--',*paths],cwd=ROOT):
                raise StorageError('source drift during native capture; no publication')
            summary=verify_daily_trace_suite(manifest,traces)
            packet={'schema_version':'assistant.daily_trace_packet.v1','manifest_digest':daily_digest(manifest),
                'source_sha':source_sha,'working_diff_sha256':hashlib.sha256(diff).hexdigest(),'traces':traces,'summary':summary}
            if args.output:
                if not summary['mechanics_met']:raise StorageError('failed tasks cannot publish a passing packet')
                with args.output.open('x') as stream:json.dump(packet,stream,ensure_ascii=False,indent=2);stream.write('\n')
        print(json.dumps(summary,sort_keys=True))
        return 0 if summary['mechanics_met'] else 1
    except (StorageError,OSError,ValueError,KeyError,AssertionError,StopIteration):
        print('daily native evaluation failed; no provider/quality/acceptance claim',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
