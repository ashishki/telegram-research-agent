"""Explicit synthetic migration CLI; no DSN/environment/default target."""
import argparse
from .postgres import SyntheticTarget,migrate,StorageError


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['migrate'])
    parser.add_argument('--backend',required=True)
    parser.add_argument('--host',required=True)
    parser.add_argument('--port',required=True,type=int)
    parser.add_argument('--database',required=True)
    parser.add_argument('--user',required=True)
    parser.add_argument('--instance-id',required=True)
    parser.add_argument('--target',required=True)
    parser.add_argument('--expected-version',required=True,type=int)
    args=parser.parse_args(argv)
    try:
        cfg=SyntheticTarget(args.backend,args.host,args.port,args.database,args.user,args.instance_id,args.target)
        version=migrate(cfg,expected_version=args.expected_version)
        print('Synthetic runtime schema version:',version)
        return 0
    except StorageError as error:
        print('Migration denied:',str(error))
        return 1


if __name__=='__main__':raise SystemExit(main())
