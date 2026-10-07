"""Exact owned academic-item to confirmed Watch subject bindings."""
import hashlib
from .postgres import PostgresStore,StorageError

DDL=(
    'CREATE SCHEMA pa_academic',
    'CREATE TABLE pa_academic.meta(version integer PRIMARY KEY,checksum text NOT NULL)',
    '''CREATE TABLE pa_academic.watches(owner text NOT NULL,object_ref text NOT NULL,schedule_id text NOT NULL,subject_ref text NOT NULL,
       PRIMARY KEY(owner,object_ref,schedule_id,subject_ref))''',
    'GRANT USAGE ON SCHEMA pa_academic TO pa_test_app',
    'GRANT SELECT ON pa_academic.meta TO pa_test_app',
    'GRANT SELECT,INSERT,DELETE ON pa_academic.watches TO pa_test_app',
)
CHECKSUM=hashlib.sha256('\n'.join(DDL).encode()).hexdigest()

def install_academic(target):
    if target.user!='pa_test_migrator':raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(87291019,))
        if tx.conn.execute("SELECT to_regclass('pa_academic.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_academic.meta VALUES(1,%s)',(CHECKSUM,))
        elif tx.conn.execute('SELECT version,checksum FROM pa_academic.meta').fetchall()!=[{'version':1,'checksum':CHECKSUM}]:raise StorageError('academic schema differs')
