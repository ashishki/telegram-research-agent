"""Disposable synthetic PostgreSQL process; never starts or changes a service."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import os
import pwd
import shutil
import shlex
import socket
import subprocess
import tempfile
import uuid

import psycopg
from psycopg import sql
from .postgres import SyntheticTarget, StorageError,require_no_ambient_pg_configuration

BIN = Path('/usr/lib/postgresql/14/bin')


class PostgresSandbox:
    def empty_database(self,name):
        target=self.target(name,'pa_test_migrator')
        with self._admin() as conn:conn.execute(sql.SQL('CREATE DATABASE {} OWNER pa_test_migrator').format(sql.Identifier(target.database)))
        return target
    def __init__(self):
        self.instance_id=uuid.uuid4().hex
        self.root=None
        self.started=False
    def _run(self,name,*args):
        command=[str(BIN/name),*map(str,args)]
        if os.geteuid()==0:command=['/usr/sbin/runuser','-u','postgres','--',*command]
        result=subprocess.run(command,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PGPASSFILE':'/dev/null'},capture_output=True,text=True,timeout=30)
        if result.returncode:raise StorageError('isolated PostgreSQL '+name+' failed')
        return result
    def __enter__(self):
        if not all((BIN/name).is_file() for name in ('initdb','pg_ctl','pg_dump','pg_restore')):
            raise StorageError('PostgreSQL 14 tools required; this test must not be skipped')
        self.root=Path(tempfile.mkdtemp(prefix='pai-postgres-'))
        if os.geteuid()==0:
            user=pwd.getpwnam('postgres');os.chown(self.root,user.pw_uid,user.pw_gid)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        try:
            self._run('initdb','-D',self.root/'db','--auth=trust','--no-locale','-E','UTF8','-U','postgres')
            options=shlex.join(['-h','127.0.0.1','-p',str(self.port),'-k',str(self.root),
                               '-c','cluster_name=pa-synthetic-'+self.instance_id,'-c','max_connections=30'])
            self.started=True
            self._run('pg_ctl','-D',self.root/'db','-l',self.root/'server.log','-o',options,'-w','start')
            with self._admin() as conn:
                conn.execute('CREATE ROLE pa_test_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION')
                conn.execute('CREATE ROLE pa_test_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION')
                conn.execute('CREATE DATABASE pa_test_runtime OWNER pa_test_migrator')
            self.migrator=self.target('pa_test_runtime','pa_test_migrator')
            self.app=self.target('pa_test_runtime','pa_test_app')
            return self
        except BaseException:
            self.__exit__(None,None,None)
            raise
    def _admin(self):
        require_no_ambient_pg_configuration()
        return psycopg.connect(host='127.0.0.1',hostaddr='127.0.0.1',port=self.port,dbname='postgres',
            user='postgres',password='',passfile='/dev/null',sslmode='disable',gssencmode='disable',
            autocommit=True,connect_timeout=3)
    def target(self,database,user):
        return SyntheticTarget('postgresql','127.0.0.1',self.port,database,user,self.instance_id,'synthetic-test')
    def restore_copy(self,database='pa_test_restored'):
        self.target(database,'pa_test_migrator')  # validate identifier/target first
        dump=self.root/'synthetic.dump'
        self._run('pg_dump','-h','127.0.0.1','-p',self.port,'-U','pa_test_migrator','-d','pa_test_runtime',
                  '--schema=pa_runtime','--no-owner','--no-privileges','-Fc','-f',dump)
        with self._admin() as conn:conn.execute(sql.SQL('CREATE DATABASE {} OWNER pa_test_migrator').format(sql.Identifier(database)))
        self._run('pg_restore','-h','127.0.0.1','-p',self.port,'-U','pa_test_migrator','-d',database,
                  '--no-owner','--no-privileges','--exit-on-error',dump)
        with self.target(database,'pa_test_migrator').connect() as conn:
            conn.execute('GRANT USAGE ON SCHEMA pa_runtime TO pa_test_app')
            conn.execute('GRANT SELECT ON pa_runtime.schema_migrations TO pa_test_app')
            conn.execute('GRANT SELECT,INSERT ON pa_runtime.object_versions TO pa_test_app')
            conn.execute('GRANT SELECT,INSERT,UPDATE ON pa_runtime.object_heads TO pa_test_app')
        return self.target(database,'pa_test_app')
    def __exit__(self,*args):
        if self.started and (self.root/'db/postmaster.pid').exists():
            self._run('pg_ctl','-D',self.root/'db','-m','immediate','-w','stop')
        self.started=False
        if self.root and self.root.exists():shutil.rmtree(self.root)
