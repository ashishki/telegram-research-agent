"""Deterministic event revisions. Similarity alone never merges two events."""
from dataclasses import dataclass
import hashlib
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


VERSION = 'deterministic-events-v1'


def canonical_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            return None
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                 if not k.casefold().startswith('utm_')]
        return urlunsplit(('https', parsed.netloc.casefold(), parsed.path or '/', urlencode(sorted(query)), ''))
    except ValueError:
        return None


def fingerprint(payload):
    # Preserve signs, case, numbers and all words. No semantic equivalence or
    # inferred deadline/entity extraction. Titles/discovery clocks are metadata.
    text = payload.get('support_span') or payload.get('text') or payload.get('content') or payload.get('summary') or ''
    text = ' '.join(str(text).split())
    revision = [text, str(payload.get('conflict_group') or ''), str(payload.get('conflict_value') or ''),
                str(payload.get('change_type') or ''), str(payload.get('event_revision') or '')]
    return hashlib.sha256('\x1f'.join(revision).encode()).hexdigest()


@dataclass(frozen=True)
class EventCluster:
    event_ref: str
    revision: str
    records: tuple
    novelty: str
    previous_brief_ref: str | None
    conflict: bool

    def metadata(self):
        urls = sorted({canonical_url(r.payload.get('canonical_url') or r.payload.get('source_url'))
                       for r in self.records} - {None})
        return {'event_ref': self.event_ref, 'revision': self.revision, 'novelty': self.novelty,
                'previous_brief_ref': self.previous_brief_ref, 'record_count': len(self.records),
                'evidence_refs': [r.evidence_ref for r in self.records[:4]],
                'source_versions': [r.source_version for r in self.records[:4]],
                'refs_complete': len(self.records) <= 4, 'all_refs_location': 'brief_material_inventory',
                'canonical_urls': urls[:4], 'reported_source_count': len(urls),
                # Exact copies cannot prove independent reporting. Do not count
                # channels/posters as corroboration.
                'independent_confirmation_count': None, 'independence': 'unverified',
                'conflict': self.conflict, 'last_surfaced_at': None,
                'mechanism': VERSION}


def cluster_events(records, *, history=()):
    if len(records) > 2048 or len(history) > 480:
        raise ValueError('bounded event input required')
    groups = {}
    for record in records:
        p = record.payload
        url = canonical_url(p.get('canonical_url') or p.get('source_url') or p.get('message_url'))
        facts = fingerprint(p)
        # URL associates revisions; identical complete bounded content can also
        # identify syndicated copies. Missing/truncated content is uncertain.
        truncated = p.get('content_truncated') is True
        text = p.get('support_span') or p.get('text') or p.get('content') or p.get('summary') or ''
        # Different explicitly identified events remain separate even when a
        # short announcement has identical wording.
        explicit=canonical_url(p.get('canonical_url'))
        key = (explicit,facts) if len(str(text).strip()) >= 16 and not truncated else (explicit,record.evidence_ref)
        groups.setdefault(key, []).append(record)
    output = []
    for key, rows in groups.items():
        urls = sorted({canonical_url(r.payload.get('canonical_url') or r.payload.get('source_url') or r.payload.get('message_url'))
                       for r in rows} - {None})
        # A primary URL is stable across factual corrections. Without a shared
        # URL only an exact content fingerprint supports grouping.
        uncertain=any(r.payload.get('content_truncated') is True for r in rows) or len(str(rows[0].payload.get('support_span') or rows[0].payload.get('text') or '').strip())<16
        family = urls[0] if len(urls) == 1 else 'fingerprint:' + key[1]
        if uncertain:family+=':uncertain:'+rows[0].evidence_ref
        event_ref = 'event_' + hashlib.sha256(family.encode()).hexdigest()[:32]
        revision = fingerprint(rows[0].payload)
        old = [h for h in history if h.get('event_ref') == event_ref or not key[0] and h.get('revision')==revision]
        same = [h for h in old if h.get('revision') == revision]
        novelty = 'uncertain' if uncertain else 'repeated' if same else 'changed' if old else 'new'
        previous = (same or old)[-1].get('brief_ref') if old else None
        own_groups = {r.payload.get('conflict_group') for r in rows} - {None, ''}
        conflict = any(len({r.payload.get('conflict_value') for r in records
                            if r.payload.get('conflict_group') == g} - {None, ''}) > 1 for g in own_groups)
        output.append(EventCluster(event_ref, revision, tuple(rows), novelty, previous, conflict))
    return tuple(sorted(output, key=lambda e: (e.event_ref, e.revision)))
