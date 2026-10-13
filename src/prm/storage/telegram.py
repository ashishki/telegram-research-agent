"""Additive route metadata in the existing version store; no new queue or DDL."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timedelta
import re
import uuid

from prm.telegram_contracts import TelegramDestination, TelegramMessageBinding
from .postgres import StorageError, StateConflict, _canonical


class TelegramBindings:
    def __init__(self, queue, *, owner, destination):
        self.queue, self.store, self.owner, self.destination = queue, queue.store, owner, destination

    def _message_ref(self, route, message_id):
        digest = _canonical({'destination': asdict(route), 'message_id': message_id})[1]
        return 'telegram_message_' + digest[:40]

    def bind_message(self, binding):
        with self.store.transaction() as tx:
            return self.bind_message_in(tx, binding)

    def bind_message_in(self, tx, binding):
        if type(binding) is not TelegramMessageBinding or (binding.owner, binding.destination) != (self.owner, self.destination):
            raise StorageError('message binding owner/route differs')
        self._lineage_lock(tx)
        job = tx.conn.execute('SELECT payload,result_ref FROM pa_jobs.jobs WHERE owner=%s AND id=%s',
                                  (self.owner, binding.job_ref)).fetchone()
        if not job: raise StorageError('bound job unavailable')
        self.queue._input(tx, self.owner, job['payload'])
        if binding.response_ref is not None:
            if job['result_ref'] != binding.response_ref or tx.get(self.owner, 'result', binding.response_ref, version=binding.response_version) is None:
                raise StorageError('bound result version unavailable')
        ref = self._message_ref(binding.destination, binding.message_id)
        payload = {'schema_version': 'telegram.message_binding.v1', **asdict(binding)}
        item = tx.get(self.owner, 'conversation', ref)
        if item:
            if item.payload != payload: raise StateConflict('Telegram message binding changed')
            return item
        item = tx.put(self.owner, 'conversation', ref, payload, expected_version=0)
        self._dependency(tx, job['payload']['input_ref'], ref)
        return item

    def _dependency(self, tx, parent_ref, child_ref):
        if tx.conn.execute("SELECT to_regclass('pa_memory.dependencies') AS table_ref").fetchone()['table_ref'] is not None:
            tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                            (self.owner, 'conversation', parent_ref, 'conversation', child_ref))

    def _lineage_lock(self, tx):
        from prm.runtime.deletion import lineage_lock
        lineage_lock(tx.conn, self.owner)

    def for_message(self, route, message_id):
        if type(message_id) is not int or message_id <= 0 or route != self.destination: return None
        item = self.store.get(self.owner, 'conversation', self._message_ref(route, message_id))
        if item is None or item.payload.get('schema_version') != 'telegram.message_binding.v1': return None
        value = dict(item.payload)
        value.pop('schema_version')
        value['destination'] = TelegramDestination(**value['destination'])
        binding = TelegramMessageBinding(**value)
        return binding if (binding.owner, binding.destination) == (self.owner, route) else None

    def issue_control(self, *, command, job_id, ttl_seconds=900):
        if command not in {'status', 'result', 'cancel'} or type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise StorageError('bounded navigation control required')
        token = uuid.uuid4().hex
        with self.store.transaction() as tx:
            self._lineage_lock(tx)
            row = tx.conn.execute('SELECT payload FROM pa_jobs.jobs WHERE owner=%s AND id=%s', (self.owner, job_id)).fetchone()
            if row is None: raise StorageError('control job unavailable')
            self.queue._input(tx, self.owner, row['payload'])
            now = tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            # Repeated ambiguity prompts reuse unexpired navigation rather than
            # growing a new dependency graph for every status request.
            existing = tx.conn.execute('''SELECT v.object_id,v.payload FROM pa_runtime.object_heads h
                JOIN pa_runtime.object_versions v USING(owner,namespace,object_id,version)
                WHERE h.owner=%s AND h.namespace='conversation'
                AND v.payload->>'schema_version'='telegram.job_control.v1'
                AND v.payload->>'job_ref'=%s AND v.payload->>'command'=%s
                ORDER BY v.created_at DESC LIMIT 16''', (self.owner, job_id, command)).fetchall()
            for item in existing:
                value = item['payload']
                if (value['destination'] == asdict(self.destination) and value['input_digest'] == row['payload']['input_digest']
                    and datetime.fromisoformat(value['expires_at']) > now):
                    return 'paic:' + item['object_id'].removeprefix('telegram_control_')
                if datetime.fromisoformat(value['expires_at']) <= now:
                    tx._object_lock(self.owner, 'conversation', item['object_id'])
                    tx.conn.execute('DELETE FROM pa_runtime.object_heads WHERE owner=%s AND namespace=%s AND object_id=%s', (self.owner, 'conversation', item['object_id']))
                    tx.conn.execute('DELETE FROM pa_runtime.object_versions WHERE owner=%s AND namespace=%s AND object_id=%s', (self.owner, 'conversation', item['object_id']))
                    if tx.conn.execute("SELECT to_regclass('pa_memory.dependencies') AS table_ref").fetchone()['table_ref'] is not None:
                        tx.conn.execute('DELETE FROM pa_memory.dependencies WHERE owner=%s AND child_namespace=%s AND child_ref=%s', (self.owner, 'conversation', item['object_id']))
            ref = 'telegram_control_' + token
            tx.put(self.owner, 'conversation', ref, {'schema_version': 'telegram.job_control.v1',
                'destination': asdict(self.destination), 'command': command, 'job_ref': job_id,
                'input_digest': row['payload']['input_digest'], 'expires_at': (now + timedelta(seconds=ttl_seconds)).isoformat()}, expected_version=0)
            self._dependency(tx, row['payload']['input_ref'], ref)
        return 'paic:' + token

    def resolve_control(self, token, *, destination):
        if destination != self.destination or not isinstance(token, str) or not re.fullmatch(r'paic:[a-f0-9]{32}', token): return None
        with self.store.transaction() as tx:
            item = tx.get(self.owner, 'conversation', 'telegram_control_' + token[5:])
            if item is None: return None
            value = item.payload
            now = tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            if (value.get('schema_version') != 'telegram.job_control.v1' or value.get('destination') != asdict(destination)
                or datetime.fromisoformat(value['expires_at']) <= now): return None
            job = tx.conn.execute('SELECT payload FROM pa_jobs.jobs WHERE owner=%s AND id=%s', (self.owner, value['job_ref'])).fetchone()
            if job is None or job['payload']['input_digest'] != value['input_digest']: return None
            try: self.queue._input(tx, self.owner, job['payload'])
            except StorageError: return None
            return value['command'], value['job_ref']
