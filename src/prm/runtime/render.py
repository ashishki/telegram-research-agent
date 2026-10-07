"""Restricted subprocess entrypoint for immutable synthetic/private reports."""
import argparse
import json
from pathlib import Path
import resource
import socket


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--format',choices=('html','markdown','pdf'),required=True);args=parser.parse_args(argv)
    resource.setrlimit(resource.RLIMIT_CPU,(12,12));resource.setrlimit(resource.RLIMIT_FSIZE,(16000000,16000000))
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64));resource.setrlimit(resource.RLIMIT_AS,(1500000000,1500000000))
    def denied(*args,**kwargs):raise RuntimeError('renderer network disabled')
    socket.socket=denied;socket.create_connection=denied
    from prm.briefs import _stored_document
    from prm.report_exports import render_report
    source=Path(args.input)
    if source.stat().st_size>256000:raise ValueError('bounded immutable render input required')
    document=_stored_document(json.loads(source.read_text()))
    artifact=render_report(document,args.format)
    body=artifact.body.encode('utf-8') if isinstance(artifact.body,str) else artifact.body
    if len(body)>16000000:raise ValueError('artifact exceeds bound')
    Path(args.output).write_bytes(body)
    return 0


if __name__=='__main__':raise SystemExit(main())
