"""Apply bounded intent proposals through existing handlers, never an executor."""
from dataclasses import replace
import hashlib
import json
import re
from prm.contracts import AssistantResult
from prm.storage.postgres import StorageError
from prm.capabilities import CapabilityDenied
from .intent_planner import validate_task_plan,TaskPlan
from .dispatch import parse_request_intent,RequestIntent,IntentKind

FOLLOWUP=re.compile(r'(?i)^(?:короче|сделай короче|коротко|поясни (?:второй|этот)|расскажи (?:про )?второй|объясни (?:этот|второй)|the second|explain (?:that|the second)|shorten)')
CLARIFY={'missing_target':'Выбери результат: ответь на нужное сообщение или укажи сохранённый документ.',
    'ambiguous_target':'Нашлось несколько возможных результатов. Ответь на нужное сообщение.',
    'source_unavailable':'Нужный источник сейчас недоступен. Выбери доступный источник или уточни задачу.',
    'missing_action_fields':'Для предпросмотра нужны точные адресат и содержание. Уточни их.',
    'uncertain_intent':'Уточни, какой результат нужен: объяснение, поиск, обзор или локальный предпросмотр.'}


def clarification(request_ref,reason):return AssistantResult(request_ref,'clarify','clarify',CLARIFY[reason],payload={'clarification_reason':reason,'source_data_class':'user_provided'})


def _read_view(root,request_ref,ticket,plan,guard):
    if ticket is None or not ticket.get('target'):return clarification(request_ref,'missing_target')
    try:item,classes,scopes=root.focus.resolve(ticket,guard=guard)
    except (StorageError,CapabilityDenied):return clarification(request_ref,'ambiguous_target' if ticket.get('ambiguous') else 'source_unavailable')
    payload=item.payload;details=payload.get('payload',{})
    text=payload.get('text',payload.get('display_text'))
    if not isinstance(text,str):return clarification(request_ref,'missing_target')
    if plan.item_index:
        items=payload.get('item_texts')
        if not items:
            refs=details.get('conversation',{}).get('response_refs',())
            source=root.queue.store.get(root.owner_ref,'result',refs[0],version=1) if refs else None
            items=source.payload.get('item_texts') if source else None
        if not items:items=[s.strip() for s in re.split(r'\n(?=(?:\d+\.\s|[-•]\s))',text) if s.strip()]
        if len(items)<plan.item_index:return clarification(request_ref,'missing_target')
        text=items[plan.item_index-1]
    elif plan.steps[0].argument=='shorten':text=text.strip().split('\n\n')[0][:800]
    return AssistantResult(request_ref,'ok','chat',text,payload={'response_ref':item.object_id,'bound_result_version':item.version,
        'source_data_classes':list(classes),'source_data_class':classes[0],'source_scopes':list(scopes),
        'conversation':{'response_refs':[item.object_id]},'task_plan':json.loads(json.dumps(plan.to_dict()))})


def apply_conversation_plan(root,request,intent,*,request_ref,lease,guard):
    ticket=root.focus.ticket(request_ref) if lease is not None else None
    if intent.origin not in {'text'} or request.mode!='auto' or request.query.strip().casefold() in {'да','yes','подтверждаю'}:return None
    if ticket and ticket.get('ambiguous'):return clarification(request_ref,'ambiguous_target')
    if lease is not None:
        with root.queue.store.transaction() as tx:body=root.queue._input(tx,root.owner_ref,lease.payload).payload
        if body.get('telegram_envelope',{}).get('source_trust')=='untrusted_source':return None
    tools=['chat.compose','archive.search','result.view']
    if 'brief' in root.services:tools.append('brief.compose')
    if hasattr(root,'actions'):tools.append('actions.preview')
    if hasattr(root,'memory'):tools.append('memory.preview')
    sources=('archive',)
    plan=None
    if root.intent_planner is not None:
        try:
            offered=root.intent_planner.propose(request.query,request_ref=request_ref,available_tools=tuple(tools),available_sources=sources,guard=guard)
            if offered is not None:
                value=offered.to_dict() if type(offered)is TaskPlan else offered
                plan=validate_task_plan(json.loads(json.dumps(value)),available_tools=tuple(tools),available_sources=sources)
        except Exception:return clarification(request_ref,'uncertain_intent')
        if plan is None:
            ref='intent_outcome_'+hashlib.sha256(request_ref.encode()).hexdigest()[:32]
            old=root.queue.store.get(root.owner_ref,'conversation',ref)
            if old is not None:return AssistantResult(request_ref,'planning_unknown','clarify','Не удалось подтвердить выбор следующего шага. Повторный вызов автоматически не выполняю.',payload={'source_data_class':'user_provided','planner_outcome':old.payload['status']})
    if plan is None and ticket and ticket.get('target') and FOLLOWUP.search(request.query):
        index=2 if re.search(r'(?i)второй|second',request.query) else None
        from .intent_planner import PlanStep,STOPS
        plan=TaskPlan('followup',(PlanStep('result.view','shorten' if re.search(r'(?i)короч|shorten',request.query) else ''),),'bound',index,None,(),False,None,1,STOPS)
    if plan is None:return None
    if lease is not None:root.focus.record_plan(request_ref,plan,guard)
    if plan.needs_clarification:return clarification(request_ref,plan.reason)
    if plan.intent=='followup':return _read_view(root,request_ref,ticket,plan,guard)
    if plan.intent=='chat':return replace(request,mode='chat'),RequestIntent(IntentKind.CHAT,request.query,'chat')
    if plan.intent=='search':
        queries=[s.argument or request.query for s in plan.steps]
        if plan.source_filters and set(plan.source_filters)!={'archive'}:return clarification(request_ref,'source_unavailable')
        command='/deep '+json.dumps({'schema_version':1,'question':request.query[:2000],'steps':[{'source':'archive','query':q} for q in queries],
            'max_tool_calls':plan.max_tool_calls,'deadline_seconds':180},ensure_ascii=False)
        return replace(request,query=command),parse_request_intent(command)
    if plan.intent=='weekly':
        query='/weekly '+(plan.steps[0].argument or request.query)
        return replace(request,query=query),parse_request_intent(query)
    if plan.intent=='memory_preview':
        content=plan.steps[0].argument
        if not content or content not in request.query:return clarification(request_ref,'uncertain_intent')
        query='/remember '+content
        return replace(request,query=query),parse_request_intent(query)
    if plan.intent=='action_preview':
        match=re.search(r'\{.*\}',request.query,re.S)
        if not match:return clarification(request_ref,'missing_action_fields')
        try:value=json.loads(match[0])
        except ValueError:return clarification(request_ref,'missing_action_fields')
        if not isinstance(value,dict) or set(value)!={'action_code','resource_ref','content'}:return clarification(request_ref,'missing_action_fields')
        query='/actpreview '+match[0]
        return replace(request,query=query),parse_request_intent(query)
    return clarification(request_ref,'uncertain_intent')
