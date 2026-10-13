"""Additive route metadata in the existing version store; no new queue or DDL."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timedelta
import hashlib
import json
import re
import uuid

from prm.telegram_contracts import TelegramDestination, TelegramMessageBinding, update_digest
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
        payload = {'schema_version': 'telegram.message_binding.v2', **asdict(binding)}
        item = tx.get(self.owner, 'conversation', ref)
        if item:
            value = dict(item.payload); value.pop('schema_version')
            value['destination'] = TelegramDestination(**value['destination'])
            if TelegramMessageBinding(**value) != binding: raise StateConflict('Telegram message binding changed')
            return item
        item = tx.put(self.owner, 'conversation', ref, payload, expected_version=0)
        self._dependency(tx, job['payload']['input_ref'], ref, job['payload']['input_namespace'])
        if binding.response_ref is not None: self._dependency(tx, binding.response_ref, ref, 'result')
        return item

    def source_ref(self, route, message_id):
        return self._message_ref(route, message_id).replace('telegram_message_', 'telegram_source_', 1)

    def source_in(self, tx, envelope):
        if envelope.message_id is None: return None, 1
        ref = self.source_ref(envelope.destination, envelope.message_id)
        tx._object_lock(self.owner, 'conversation', ref)
        prior = tx.get(self.owner, 'conversation', ref)
        if prior:
            if prior.payload['input_digest'] != envelope.input_digest: raise StateConflict('source message identity reused without revision')
            return ref, prior.version
        tx.put(self.owner, 'conversation', ref, {'schema_version': 'telegram.source.v2',
            'input_digest': envelope.input_digest, 'update_id': envelope.update_id}, expected_version=0)
        return ref, 1

    def request_current_in(self, tx, item):
        metadata = item.payload.get('telegram_envelope', {})
        refs = [(metadata.get('source_revision_ref'), metadata.get('source_revision'))]
        reply = item.payload.get('reply_target', {})
        refs.append((reply.get('source_revision_ref'), reply.get('source_revision')))
        for ref, version in refs:
            if ref is None: continue  # Legacy inputs have no v2 source pointer.
            source = tx.get(self.owner, 'conversation', ref)
            if source is None or source.version != version: raise StateConflict('Telegram source revision is stale or deleted')

    def revise_source(self, update, envelope):
        if envelope.message_id is None: raise StorageError('edited message requires its original message identity')
        ref = self.source_ref(envelope.destination, envelope.message_id)
        with self.store.transaction() as tx:
            self._lineage_lock(tx); self.update_identity_in(tx, update)
            tx._object_lock(self.owner, 'conversation', ref)
            prior = tx.get(self.owner, 'conversation', ref)
            if prior and prior.payload.get('update_id') == envelope.update_id:
                return prior.version
            if tx._deleted(self.owner, 'conversation', ref): raise StateConflict('deleted source cannot be revised')
            binding = tx.get(self.owner, 'conversation', self._message_ref(envelope.destination, envelope.message_id))
            if binding:
                job_ref = binding.payload['job_ref']
                job = tx.conn.execute('SELECT payload FROM pa_jobs.jobs WHERE owner=%s AND id=%s', (self.owner, job_ref)).fetchone()
                if job:
                    tx.conn.execute("""UPDATE pa_jobs.jobs SET status=CASE WHEN mode='effect' AND attempts>0 THEN 'awaiting_reconciliation' ELSE 'cancelled' END,
                        token=NULL,lease_until=NULL WHERE owner=%s AND id=%s AND status IN ('queued','leased','running','retry_wait')""", (self.owner, job_ref))
                    if tx.conn.execute("SELECT to_regclass('pa_actions.proposals') AS meta").fetchone()['meta'] is not None:
                        tx.conn.execute("UPDATE pa_actions.proposals SET status='cancelled' WHERE owner=%s AND status IN ('prepared','consumed') AND (payload->'rationale_refs') ? %s",
                            (self.owner, 'user_request:' + job['payload']['input_ref']))
            revision_ref = 'telegram_revision_' + hashlib.sha256((self.destination.bot_ref + ':' + str(envelope.update_id)).encode()).hexdigest()[:32]
            text = update['edited_message'].get('text', update['edited_message'].get('caption', ''))
            tx.put(self.owner, 'conversation', revision_ref, {'schema_version': 'telegram.source_revision.v2',
                'text': text, 'envelope': asdict(envelope)}, expected_version=0)
            source = tx.put(self.owner, 'conversation', ref, {'schema_version': 'telegram.source.v2',
                'input_digest': envelope.input_digest, 'update_id': envelope.update_id, 'revision_ref': revision_ref}, expected_version=prior.version if prior else 0)
            self._dependency(tx, ref, revision_ref)
            return source.version

    def _dependency(self, tx, parent_ref, child_ref, parent_namespace='conversation'):
        if tx.conn.execute("SELECT to_regclass('pa_memory.dependencies') AS table_ref").fetchone()['table_ref'] is not None:
            tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                            (self.owner, parent_namespace, parent_ref, 'conversation', child_ref))

    def _lineage_lock(self, tx):
        from prm.runtime.deletion import lineage_lock
        lineage_lock(tx.conn, self.owner)

    def update_identity_ref(self, update_id):
        return 'telegram_update_' + hashlib.sha256((self.destination.bot_ref + ':' + str(update_id)).encode()).hexdigest()[:32]

    def update_identity_in(self, tx, update):
        try:
            raw = json.dumps(update, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
        except (TypeError, ValueError, RecursionError):
            raise StorageError('bounded immutable update required') from None
        if len(raw) > 65536: raise StorageError('update exceeds bound')
        digest = hashlib.sha256(raw).hexdigest()
        self.identity_digest_in(tx, update['update_id'], digest)
        return digest

    def identity_digest_in(self, tx, update_id, digest, *, allow_conflict=False):
        ref = self.update_identity_ref(update_id)
        tx._object_lock(self.owner, 'conversation', ref)
        prior = tx.get(self.owner, 'conversation', ref)
        if prior:
            if prior.payload['input_digest'] != digest and not allow_conflict: raise StateConflict('update ID reused with different content')
        else:
            # Minimal no-replay identity intentionally has no source text. A
            # source deletion must not make its immutable update ID reusable.
            tx.put(self.owner, 'conversation', ref, {'schema_version': 'telegram.update_identity.v1', 'input_digest': digest}, expected_version=0)

    def freeze_control_selection(self, update, resolve):
        """Commit the exact target/ambiguity before an idempotent job control.

        A crash after cancellation must never resolve the next remaining job.
        The stored fingerprint binds the entire immutable update, without
        retaining another copy of its text or source metadata.
        """
        try:
            raw = json.dumps(update, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
        except (TypeError, ValueError, RecursionError):
            raise StorageError('bounded immutable control update required') from None
        if len(raw) > 65536: raise StorageError('control update exceeds bound')
        digest = hashlib.sha256(raw).hexdigest()
        ref = 'telegram_control_input_' + hashlib.sha256((self.destination.bot_ref + ':' + str(update['update_id'])).encode()).hexdigest()[:32]
        with self.store.transaction() as tx:
            self._lineage_lock(tx)
            self.update_identity_in(tx, update)
            tx._object_lock(self.owner, 'conversation', ref)
            item = tx.get(self.owner, 'conversation', ref)
            if item:
                if item.payload['input_digest'] != digest: raise StateConflict('control update ID reused with different content')
                return item.payload['selection']
            selection = asdict(resolve())
            tx.put(self.owner, 'conversation', ref, {'schema_version': 'telegram.control_intake.v1',
                'input_digest': digest, 'selection': selection}, expected_version=0)
            jobs = {item['job_ref'] for item in selection['candidates']}
            if selection['job_ref']: jobs.add(selection['job_ref'])
            for job_ref in jobs:
                job = tx.conn.execute('SELECT payload FROM pa_jobs.jobs WHERE owner=%s AND id=%s', (self.owner, job_ref)).fetchone()
                if job is not None:
                    self.queue._input(tx, self.owner, job['payload'])
                    self._dependency(tx, job['payload']['input_ref'], ref, job['payload']['input_namespace'])
            return selection

    def for_message(self, route, message_id):
        if type(message_id) is not int or message_id <= 0 or route != self.destination: return None
        item = self.store.get(self.owner, 'conversation', self._message_ref(route, message_id))
        if item is None or item.payload.get('schema_version') not in {'telegram.message_binding.v1', 'telegram.message_binding.v2'}: return None
        value = dict(item.payload)
        value.pop('schema_version')
        value['destination'] = TelegramDestination(**value['destination'])
        binding = TelegramMessageBinding(**value)
        if (binding.owner, binding.destination) != (self.owner, route): return None
        with self.store.transaction() as tx:
            row = tx.conn.execute('SELECT payload FROM pa_jobs.jobs WHERE owner=%s AND id=%s', (self.owner, binding.job_ref)).fetchone()
            if row is None: return None
            try:
                self.queue._input(tx, self.owner, row['payload'])
                if binding.source_revision_ref:
                    source = tx.get(self.owner, 'conversation', binding.source_revision_ref)
                    if source is None or source.version != binding.source_revision: return None
            except StorageError: return None
        return binding

    def issue_control(self, *, command, job_id, ttl_seconds=900, response_ref=None, response_version=None):
        if command not in {'status', 'result', 'cancel'} or type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise StorageError('bounded navigation control required')
        if (response_ref is None) != (response_version is None) or (response_version is not None and (type(response_version) is not int or response_version <= 0)):
            raise StorageError('paired result version required')
        token = uuid.uuid4().hex
        with self.store.transaction() as tx:
            self._lineage_lock(tx)
            row = tx.conn.execute('SELECT payload,result_ref FROM pa_jobs.jobs WHERE owner=%s AND id=%s', (self.owner, job_id)).fetchone()
            if row is None: raise StorageError('control job unavailable')
            if response_ref is not None and row['result_ref'] != response_ref: raise StorageError('control result differs from job')
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
                    and (value.get('response_ref'), value.get('response_version')) == (response_ref, response_version)
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
                'response_ref': response_ref, 'response_version': response_version,
                'input_digest': row['payload']['input_digest'], 'expires_at': (now + timedelta(seconds=ttl_seconds)).isoformat()}, expected_version=0)
            self._dependency(tx, row['payload']['input_ref'], ref, row['payload']['input_namespace'])
            if response_ref is not None:
                if tx.get(self.owner, 'result', response_ref, version=response_version) is None: raise StorageError('control result version unavailable')
                self._dependency(tx, response_ref, ref, 'result')
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
            if value.get('response_ref') is not None and tx.get(self.owner, 'result', value['response_ref'], version=value['response_version']) is None: return None
            return value['command'], value['job_ref']


class TelegramInbox:
    """Durable decisions/cursor and precommitted immediate-reply attempts."""
    def __init__(self, bindings):
        self.bindings, self.store, self.owner = bindings, bindings.store, bindings.owner
        self.cursor_ref = 'telegram_cursor_' + hashlib.sha256(bindings.destination.bot_ref.encode()).hexdigest()[:32]

    def polling_offset(self):
        row = self.store.get(self.owner, 'conversation', self.cursor_ref)
        return row.payload['offset'] if row else None

    def guard_identity(self, update):
        prior = self.store.get(self.owner, 'conversation', self.bindings.update_identity_ref(update['update_id']))
        if prior and prior.payload['input_digest'] != update_digest(update): raise StateConflict('update ID reused with different content')

    def begin_once(self, update):
        """Immediate local Watch controls cannot be repeated after a crash."""
        ref = 'telegram_once_' + hashlib.sha256((self.bindings.destination.bot_ref + ':' + str(update['update_id'])).encode()).hexdigest()[:32]
        with self.store.transaction() as tx:
            self.bindings._lineage_lock(tx); self.bindings.update_identity_in(tx, update)
            tx._object_lock(self.owner, 'conversation', ref)
            if tx.get(self.owner, 'conversation', ref) is not None: return False
            tx.put(self.owner, 'conversation', ref, {'schema_version': 'telegram.once.v2', 'input_digest': update_digest(update)}, expected_version=0)
            return True

    def _cursor_in(self, tx, update_id):
        tx._object_lock(self.owner, 'conversation', self.cursor_ref)
        old = tx.get(self.owner, 'conversation', self.cursor_ref)
        offset = max(update_id + 1, old.payload['offset'] if old else 0)
        tx.put(self.owner, 'conversation', self.cursor_ref, {'schema_version': 'telegram.cursor.v2', 'offset': offset}, expected_version=old.version if old else 0)

    def record_decision(self, update, *, kind, disposition, reply=None, quarantined=False):
        digest = update_digest(update, maximum=1048576 if quarantined else 65536)
        suffix = hashlib.sha256((self.bindings.destination.bot_ref + ':' + str(update['update_id']) + (':' + digest if quarantined else '')).encode()).hexdigest()[:32]
        ref = ('telegram_quarantine_' if quarantined else 'telegram_inbox_') + suffix
        with self.store.transaction() as tx:
            self.bindings._lineage_lock(tx); tx._object_lock(self.owner, 'conversation', ref)
            self.bindings.identity_digest_in(tx, update['update_id'], digest, allow_conflict=quarantined)
            old = tx.get(self.owner, 'conversation', ref)
            if old:
                if old.payload['input_digest'] != digest: raise StateConflict('inbox update ID reused with different content')
            else:
                now = tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
                tx.put(self.owner, 'conversation', ref, {'schema_version': 'telegram.inbox.v2',
                    'update_id': update['update_id'], 'kind': kind, 'input_digest': digest,
                    'disposition': disposition, 'received_at': now.isoformat(),
                    'request_ref': reply.request_ref if reply else None, 'job_ref': reply.job_id if reply else None}, expected_version=0)
            self._cursor_in(tx, update['update_id'])

    def prepare_reply(self, update, reply):
        if reply.destination is None: raise StorageError('exact intake reply destination required')
        ref = 'telegram_intake_reply_' + hashlib.sha256((self.bindings.destination.bot_ref + ':' + str(update['update_id'])).encode()).hexdigest()[:32]
        value = {'schema_version': 'telegram.intake_reply.v2', 'telegram_method': 'sendMessage',
            'destination': asdict(reply.destination), 'text': reply.text, 'navigation': reply.navigation,
            'job_ref': reply.job_id, 'input_digest': update_digest(update)}
        digest = _canonical(value)[1]
        with self.store.transaction() as tx:
            self.bindings._lineage_lock(tx); tx._object_lock(self.owner, 'conversation', ref)
            old = tx.get(self.owner, 'conversation', ref)
            if old:
                # Status can advance on replay; the actual attempted reply is
                # immutable and is never resent, including after ack loss.
                if old.payload['input_digest'] != value['input_digest']: raise StateConflict('reply update identity changed')
                return ref, False
            tx.put(self.owner, 'conversation', ref, {**value, 'digest': digest, 'status': 'unknown'}, expected_version=0)
            for job_ref in set(reply.source_job_refs + ((reply.job_id,) if reply.job_id else ())):
                job = tx.conn.execute('SELECT payload FROM pa_jobs.jobs WHERE owner=%s AND id=%s', (self.owner, job_ref)).fetchone()
                if job: self.bindings._dependency(tx, job['payload']['input_ref'], ref, job['payload']['input_namespace'])
            return ref, True

    def dispatch_reply(self, ref, reply, send):
        with self.store.transaction() as tx:
            self.bindings._lineage_lock(tx); tx._object_lock(self.owner, 'conversation', ref)
            current = tx.get(self.owner, 'conversation', ref)
            if current is None or current.payload['status'] != 'unknown': raise StorageError('intake reply was deleted or settled')
            for job_ref in set(reply.source_job_refs + ((reply.job_id,) if reply.job_id else ())):
                row = tx.conn.execute('SELECT payload FROM pa_jobs.jobs WHERE owner=%s AND id=%s', (self.owner, job_ref)).fetchone()
                if row is None: raise StorageError('intake reply source unavailable')
                self.bindings.queue._input(tx, self.owner, row['payload'])
            return send()

    def settle_reply(self, ref, reply, receipt):
        from prm.runtime.delivery import TransportReceipt
        from prm.telegram_contracts import TelegramOutcome
        if type(receipt) is TelegramOutcome and receipt.kind == 'known_rejected':
            with self.store.transaction() as tx:
                self.bindings._lineage_lock(tx)
                current = tx.get(self.owner, 'conversation', ref)
                if current and current.payload['status'] == 'unknown':
                    tx.put(self.owner, 'conversation', ref, {**current.payload, 'status': 'not_sent',
                        'error_code': receipt.error_code, 'retry_after': receipt.retry_after}, expected_version=current.version)
            return
        if type(receipt) is not TransportReceipt or receipt.destination != reply.destination or receipt.method != 'sendMessage' or type(receipt.message_id) is not int or receipt.message_id <= 0:
            return  # Missing/ambiguous acknowledgement stays unknown.
        with self.store.transaction() as tx:
            self.bindings._lineage_lock(tx)
            current = tx.get(self.owner, 'conversation', ref)
            if current is None or current.payload['status'] != 'unknown': return
            if reply.job_id:
                self.bindings.bind_message_in(tx, TelegramMessageBinding(self.owner, reply.destination, receipt.message_id,
                    reply.job_id, origin_kind='bot', delivery_ref=ref))
            tx.put(self.owner, 'conversation', ref, {**current.payload, 'status': 'sent', 'provider_receipt': receipt.provider_receipt,
                'message_id': receipt.message_id}, expected_version=current.version)
