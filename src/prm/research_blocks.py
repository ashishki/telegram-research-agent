"""Typed supported blocks; bounded lexical proofs do not claim general NLI."""
from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib,json,re
from assistant.claim_ledger import verify_answer_against_evidence
from prm.storage.postgres import StorageError

VOCABULARY_VERSION='fact-projection-v3'
WORDS={
    'service':'service','сервис':'service','reduced':'reduce','reduce':'reduce','сократил':'reduce','сократила':'reduce',
    'latency':'latency','задержку':'latency','задержка':'latency','to':'to','до':'to',
    'milliseconds':'millisecond','миллисекунд':'millisecond','миллисекунды':'millisecond',
    'did':'','not':'not','не':'not','no':'not','нет':'not','never':'not','никогда':'not','without':'not','без':'not',
    'the':'','a':'','an':'','is':'','was':'','and':'and','и':'and',
}
TOKEN=re.compile(r'[+-]?\d+(?:[.,]\d+)?|[a-zа-яё][a-zа-яё0-9_+-]*(?:\.[0-9]+)*',re.I)
IDENTIFIER=re.compile(r'[a-z][a-z0-9_]{0,39}')
QUALIFIERS=frozenset({'may','might','could','would','will','can','if','unknown','unmeasured','unverified','estimated','planned','expected','assumed','claims','claimed','reported','reports','says','said','reportedly','allegedly',
    'может','могут','возможно','если','неизвестно','неизвестен','неизмерен','предполагается','планируется','ожидается','оценочно','заявляет','утверждает','сообщил','сообщает','якобы'})


@dataclass(frozen=True)
class ResearchBlock:
    id: str
    kind: str
    text: str
    source_refs: tuple[str,...]
    premises: tuple[str,...]=()
    quote: str | None=None
    uncertainty: str | None=None
    goal: str | None=None
    conditions: tuple[str,...]=()


def tokens(text):
    import unicodedata
    text=''.join(c for c in unicodedata.normalize('NFKC',text) if unicodedata.category(c)!='Cf')
    text=text.translate(str.maketrans({'−':'-','﹣':'-','－':'-','➖':'-','⁻':'-','₋':'-'}))
    text=re.sub(r'(?<!\w)([+-])\s+(?=\d)',r'\1',text)
    text=re.sub(r"\b(can't|cannot)\b",'can not',text.casefold())
    text=re.sub(r"\b(didn't|doesn't|don't|isn't|aren't|wasn't|weren't)\b",'not',text)
    return tuple(v for raw in TOKEN.findall(text) if (v:=WORDS.get(raw,raw)))


def _source_context_matches(statement,quote,span):
    """A quote crop cannot erase the surrounding sentence's critical slots."""
    boundaries=[0,*[m.end() for m in re.finditer(r'(?<=[.!?])\s+|[\r\n]+',span)],len(span)]
    position=span.find(quote)
    candidate=tokens(statement)
    roles={'сервис':'service','компания':'company','проект':'project','модель':'model'}
    def actor(value):
        match=re.search(r'\b(service|сервис|company|компания|project|проект|model|модель)\s+([a-zа-яё0-9_-]{2,})',value,re.I)
        return (roles.get(match[1].casefold(),match[1].casefold()),match[2].casefold()) if match else None
    def first_name(value):
        names=re.findall(r'\b[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9_-]{2,}\b',value)
        generic={'service','сервис','company','компания','project','проект','model','модель','the','according'}
        return next((n.casefold() for n in names if n.casefold() not in generic),None)
    while position>=0:
        start=max(b for b in boundaries if b<=position);end=min(b for b in boundaries if b>=position+len(quote))
        context=span[start:end];source=tokens(context);subject=actor(context);name=first_name(context)
        numeric=lambda ts:tuple(t for t in ts if re.fullmatch(r'[+-]?\d+(?:[.,]\d+)?',t))
        if (('not' in source)==('not' in candidate) and (set(source)&QUALIFIERS)==(set(candidate)&QUALIFIERS)
            and (not numeric(candidate) or numeric(candidate)==numeric(source))
            and (subject is None or actor(statement)==subject) and (name is None or name in candidate)):
            return context
        position=span.find(quote,position+1)
    return None


def fact_proof(statement,quote,url,evidence):
    if not all(isinstance(v,str) for v in (statement,quote,url)) or not 1<=len(statement)<=420 or not 12<=len(quote)<=1200:return None
    if not url.startswith('https://') or not any(i.get('source_url')==url and isinstance(i.get('support_span'),str) and quote in i['support_span'] for i in evidence):return None
    context=next((context for item in evidence if item.get('source_url')==url and isinstance(item.get('support_span'),str)
        and (context:=_source_context_matches(statement,quote,item['support_span'])) is not None),None)
    if context is None:return None
    candidate=tokens(statement);support=tokens(quote)
    if len(candidate)<3 or ('not' in candidate)!=('not' in support):return None
    if (set(support)&QUALIFIERS)!=(set(candidate)&QUALIFIERS):return None
    # Only a contiguous prefix may be shortened. Interior deletion can move a
    # number into another role or turn reported speech into a measured fact.
    if candidate!=support[:len(candidate)]:return None
    if any(re.fullmatch(r'[+-]?\d+(?:[.,]\d+)?',t) for t in candidate) and candidate!=support:return None
    # Critical actors/numbers and word order are preserved by the token proof.
    # The legacy ledger checks the same mechanical projection, not an invented
    # semantic equivalence. Raw final text and exact quote stay in the block.
    projected=' '.join(candidate)+' ('+url+').'
    check=verify_answer_against_evidence(projected,[{'source_url':url,'support_span':' '.join(support)}])
    metrics=check['metrics']
    if not check['verification_complete'] or check['claim_count']!=1 or metrics['unsupported_claim_rate'] or metrics['citation_integrity']!=1:return None
    return {'mechanism':VOCABULARY_VERSION,'quote_digest':hashlib.sha256(quote.encode()).hexdigest(),
        'sentence_context_digest':hashlib.sha256(context.encode()).hexdigest(),'projection_check':check}


def assess_blocks(text,evidence,*,question=''):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('duplicate key')
            value[key]=item
        return value
    if not isinstance(text,str) or len(text.encode())>32000:return None
    try:value=json.loads(text,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('constant')))
    except (ValueError,RecursionError):return None
    if isinstance(value,dict) and set(value)=={'findings'}:
        rows=value['findings']
        if not isinstance(rows,list) or not 1<=len(rows)<=6:return None
        rows=[dict(row,id='f'+str(index),kind='fact') if isinstance(row,dict) else row for index,row in enumerate(rows,1)]
    elif isinstance(value,dict) and set(value)=={'schema_version','blocks'} and type(value['schema_version'])is int and value['schema_version']==1:rows=value['blocks']
    else:return None
    if not isinstance(rows,list) or not 1<=len(rows)<=12:return None
    ids=[r.get('id') for r in rows if isinstance(r,dict)]
    if len(ids)!=len(rows) or any(not isinstance(i,str) or not IDENTIFIER.fullmatch(i) for i in ids) or len(set(ids))!=len(ids):return None
    blocks=[];rejected=[];facts={};proofs={}
    for row in rows:
        if row.get('kind')!='fact':continue
        proof=fact_proof(row.get('text'),row.get('quote'),row.get('source_url'),evidence) if set(row)=={'id','kind','text','quote','source_url'} else None
        if proof is None:rejected.append({'id':row['id'],'kind':'fact','reason':'unsupported_quote_or_projection'});continue
        block=ResearchBlock(row['id'],'fact',row['text'].strip(),(row['source_url'],),quote=row['quote'])
        blocks.append(block);facts[row['id']]=block;proofs[row['id']]=proof
    if not facts:return None
    conflicts=[]
    fact_rows=list(facts.values())
    for index,left in enumerate(fact_rows):
        for right in fact_rows[index+1:]:
            a=tokens(left.text);b=tokens(right.text)
            base=lambda ts:tuple(t for t in ts if t!='not' and not re.fullmatch(r'\d+(?:[.,]\d+)?',t))
            if base(a)==base(b) and a!=b:conflicts.append((left.id,right.id))
    for row in rows:
        kind=row.get('kind')
        if kind=='fact':continue
        premises=row.get('premises')
        valid=isinstance(premises,list) and 1<=len(premises)<=6 and all(isinstance(i,str) and i in facts for i in premises) and len(set(premises))==len(premises)
        refs=tuple(dict.fromkeys(ref for i in premises for ref in facts[i].source_refs)) if valid else ()
        if kind=='inference' and set(row)=={'id','kind','premises','relation','uncertainty'} and valid and isinstance(row['relation'],str) and row['relation'] in {'hypothesis','needs_measurement','source_conflict'} and isinstance(row['uncertainty'],str) and row['uncertainty'] in {'preliminary','requires_measurement'}:
            if row['relation']=='source_conflict' and not any(set(pair)<=set(premises) for pair in conflicts):valid=False
            if valid:
                labels={'hypothesis':'Гипотеза по указанным фактам; связь и эффект не установлены.',
                    'needs_measurement':'Эти факты не доказывают результат применения; нужна отдельная проверка.',
                    'source_conflict':'В процитированных формулировках есть различие; требуется сверка первоисточников.'}
                blocks.append(ResearchBlock(row['id'],kind,labels[row['relation']],refs,tuple(premises),uncertainty=row['uncertainty']));continue
        if kind=='recommendation' and set(row)=={'id','kind','premises','goal','conditions','action'} and valid:
            goal=row['goal'];conditions=row['conditions'];action=row['action']
            if (isinstance(goal,str) and 1<=len(goal)<=200 and goal in question and isinstance(conditions,list)
                and conditions and len(conditions)<=6 and all(isinstance(i,str) and i in premises for i in conditions)
                and isinstance(action,str) and action in {'verify_source','compare_sources','run_local_experiment'}):
                labels={'verify_source':'Сверь выбранный первоисточник.', 'compare_sources':'Сравни процитированные источники.',
                    'run_local_experiment':'Предложение: проведи ограниченный локальный эксперимент и измерь результат.'}
                blocks.append(ResearchBlock(row['id'],kind,labels[action],refs,tuple(premises),goal=goal,conditions=tuple(conditions),uncertainty='requires_measurement'));continue
        rejected.append({'id':row['id'],'kind':kind if isinstance(kind,str) else 'invalid','reason':'missing_or_unverified_premise_or_fields'})
    rendered=[]
    for block in blocks:
        if block.kind=='fact':rendered.append(block.text.rstrip('.!? ')+' ('+block.source_refs[0]+').')
        else:
            label='Вывод (предварительно)' if block.kind=='inference' else 'Предложение'
            rendered.append(label+': '+block.text+' Основания: '+', '.join(block.premises)+'.'+(' Цель: '+block.goal if block.goal else ''))
    if rejected:rendered.append('Не удалось подтвердить часть предложенных утверждений: '+str(len(rejected))+'.')
    if conflicts:rendered.append('Процитированные формулировки расходятся; единого результата не подтверждаю.')
    source_refs=list(dict.fromkeys(ref for block in blocks for ref in block.source_refs))
    verification={'schema_version':'assistant.research_block_verification.v1','mechanism':VOCABULARY_VERSION,
        'claim_count':len(facts),'verification_complete':True,'claims':[{'claim_text':b.text,'evidence_refs':list(b.source_refs),'support_status':'supported','block_id':b.id} for b in facts.values()],
        'metrics':{'unsupported_claim_rate':0,'citation_integrity':1},'proofs':proofs}
    return {'schema_version':'assistant.research_blocks.v1','status':'partial_supported' if rejected or conflicts else 'synthesized_verified',
        'text':'\n\n'.join(rendered),'blocks':[asdict(b) for b in blocks],'rejected_blocks':rejected,
        'conflicts':[list(pair) for pair in conflicts],'source_refs':source_refs,'verification':verification}
