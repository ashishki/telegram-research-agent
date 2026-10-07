"""Durable owner-bound file references; SQL deletion precedes physical cleanup."""
import hashlib
from .postgres import PostgresStore,StorageError

DDL=(
    'CREATE SCHEMA pa_artifacts',
    'CREATE TABLE pa_artifacts.meta(version integer PRIMARY KEY,checksum text NOT NULL)',
    '''CREATE TABLE pa_artifacts.files(owner text NOT NULL,key text NOT NULL,parent_namespace text NOT NULL,parent_ref text NOT NULL,
       root_digest text NOT NULL,content_digest text NOT NULL,deleted boolean NOT NULL DEFAULT false,
       cleanup_pending boolean NOT NULL DEFAULT false,PRIMARY KEY(owner,key))''',
    'GRANT USAGE ON SCHEMA pa_artifacts TO pa_test_app',
    'GRANT SELECT ON pa_artifacts.meta TO pa_test_app',
    'GRANT SELECT,INSERT,UPDATE,DELETE ON pa_artifacts.files TO pa_test_app',
)
CHECKSUM=hashlib.sha256('\n'.join(DDL).encode()).hexdigest()

def install_artifacts(target):
    if target.user!='pa_test_migrator':raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(87291015,))
        if tx.conn.execute("SELECT to_regclass('pa_artifacts.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_artifacts.meta VALUES(1,%s)',(CHECKSUM,))
        elif tx.conn.execute('SELECT version,checksum FROM pa_artifacts.meta').fetchall()!=[{'version':1,'checksum':CHECKSUM}]:raise StorageError('artifact schema differs')
