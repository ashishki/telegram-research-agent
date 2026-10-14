"""Explicit, version-bound feedback; emoji identity never means negative interest."""
from dataclasses import dataclass,asdict
import re

KINDS=frozenset({'useful','not_topic','known','too_long','incorrect','applied','read','tried','reaction_interest','unknown'})
FEATURES={'useful':'interest','not_topic':'topic_applicability','known':'novelty','too_long':'reading_cost','incorrect':'reliability','applied':'application','read':'learning_state','tried':'learning_state','reaction_interest':'interest','unknown':'unknown'}
LABELS={'полезно':'useful','не тема':'not_topic','не моя тема':'not_topic','уже знал':'known','длинно':'too_long','слишком подробно':'too_long','неверно':'incorrect','применил':'applied'}


@dataclass(frozen=True)
class FeedbackEvent:
    owner_ref:str
    brief_id:str
    brief_version:int
    content_digest:str
    kind:str
    observed_at:str
    story_number:int|None=None
    emoji:tuple[str,...]=()
    origin:str='explicit_owner'
    schema_version:str='assistant.feedback_event.v1'

    def __post_init__(self):
        from prm.briefs import _BRIEF_ID,_CONTENT_DIGEST
        if (not isinstance(self.owner_ref,str) or not 1<=len(self.owner_ref)<=128 or not re.fullmatch(r'brief_[a-f0-9]+',self.brief_id)
            or type(self.brief_version)is not int or self.brief_version<1 or not _CONTENT_DIGEST.fullmatch(self.content_digest)
            or self.kind not in KINDS or self.origin not in {'explicit_owner','personal_reaction','legacy_explicit','legacy_reaction'}
            or self.story_number is not None and (type(self.story_number)is not int or not 1<=self.story_number<=20)
            or len(self.emoji)>8 or any(not isinstance(e,str) or not 1<=len(e)<=128 for e in self.emoji)):raise ValueError('bounded exact feedback event required')
        from datetime import datetime
        if datetime.fromisoformat(self.observed_at).tzinfo is None:raise ValueError('aware feedback observation required')
        if self.origin.endswith('reaction') and self.kind not in {'reaction_interest','unknown'}:raise ValueError('reaction cannot assert an explicit learning state')
        if self.kind=='applied' and self.origin not in {'explicit_owner','legacy_explicit'}:raise ValueError('application needs explicit owner evidence')

    def to_dict(self):
        return {**asdict(self),'emoji':list(self.emoji),'feature':FEATURES[self.kind],
            'interest':'positive' if self.kind in {'useful','reaction_interest'} else 'unknown',
            'learning_state':self.kind if self.kind in {'read','tried','applied'} else 'unknown',
            'profile_changed':False,'confirmation_authority':False}


def from_legacy_feedback(row,*,owner_ref,brief_id,brief_version,content_digest,observed_at,personal_reaction=False):
    """Caller supplies authenticated exact binding; never infer versions from text."""
    if not isinstance(row,dict):raise ValueError('explicit legacy feedback row required')
    if personal_reaction:
        emojis=tuple(str(e) for e in row.get('emoji',()))
        return FeedbackEvent(owner_ref,brief_id,brief_version,content_digest,'reaction_interest' if emojis else 'unknown',observed_at,
            row.get('story_number'),emojis,'legacy_reaction')
    label=str(row.get('feedback_type',row.get('feedback',row.get('kind','')))).casefold()
    mapping={'useful':'useful','decision_impacting':'useful','not_interested':'not_topic','duplicate_content':'known','too_long':'too_long',
        'applied_to_project':'applied','read':'read','tried':'tried','weak':'unknown','noisy':'unknown','too_shallow':'unknown',
        'confusing_visual':'unknown','missing_visual':'unknown','wrong_priority':'unknown','trust_too_high':'unknown','verify_first':'unknown'}
    kind=row.get('kind') or mapping.get(label) or LABELS.get(label)
    if kind not in KINDS-{'reaction_interest'}:raise ValueError('legacy explicit feedback kind unavailable')
    return FeedbackEvent(owner_ref,brief_id,brief_version,content_digest,kind,observed_at,row.get('story_number'),origin='legacy_explicit')


def validate_preference_rule(rule):
    allowed={'topic','signal'}
    if (not isinstance(rule,dict) or set(rule)!=allowed or not isinstance(rule['topic'],str) or not 1<=len(rule['topic'].strip())<=120
        or any(c in rule['topic'] for c in ('\n','\x00','*')) or rule['signal'] not in {'useful','not_topic','known','too_long','incorrect'}):raise ValueError('one explicit bounded topic preference required')
    return {'topic':' '.join(rule['topic'].split()).casefold(),'signal':rule['signal']}


def preference_signal(record,rules):
    topics={str(t).casefold().strip() for t in record.payload.get('topic_labels',record.payload.get('topics',()))}
    matches=[item for item in rules if item.payload['preference_rule']['topic'] in topics]
    signals=[item.payload['preference_rule']['signal'] for item in matches]
    adjustment=sum(1 if s in {'not_topic','known'} else -1 if s=='useful' else 0 for s in signals)
    return {'adjustment':max(-2,min(2,adjustment)),'features':list(dict.fromkeys(FEATURES[s] for s in signals)),
        'rule_bindings':[{'memory_ref':i.object_id,'version':i.version,'digest':i.digest} for i in matches],
        'basis':'explicit_confirmed_topic_rules' if matches else 'no_confirmed_rule','no_reaction':'unknown'}
