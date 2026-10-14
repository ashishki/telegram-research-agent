"""Pure no-media Telegram rich projection of immutable report/answer content."""
from dataclasses import dataclass
import json
import re
from urllib.parse import urlsplit
from prm.briefs import BriefDocument

MAX_CHARACTERS=32768
MAX_BLOCKS=500
MAX_DEPTH=16
MAX_COLUMNS=20
MAX_MEDIA=50


class RichMessageInvalid(ValueError):pass


def _url(value,allowed):
    if not isinstance(value,str) or len(value)>4096 or any(c in value for c in ('\x00','\n','\r')):raise RichMessageInvalid('bounded source URL required')
    parsed=urlsplit(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or value not in allowed:raise RichMessageInvalid('URL outside exact source set')


def validate_rich_message(value,*,source_urls=(),callback_tokens=(),maximum_characters=MAX_CHARACTERS):
    if (not isinstance(value,dict) or set(value)!={'blocks','skip_entity_detection'} or value['skip_entity_detection']is not True
        or not isinstance(value['blocks'],list) or not value['blocks']):raise RichMessageInvalid('server-built blocks required')
    if type(maximum_characters)is not int or not 64<=maximum_characters<=MAX_CHARACTERS:raise RichMessageInvalid('bounded text budget required')
    count=0;characters=0;references=set()
    def text(node,depth):
        nonlocal characters
        if depth>MAX_DEPTH:raise RichMessageInvalid('nested rich formatting exceeds bound')
        if isinstance(node,str):
            if '\x00' in node:raise RichMessageInvalid('invalid rich text')
            characters+=len(node);return
        if isinstance(node,list):
            for item in node:text(item,depth+1)
            return
        if not isinstance(node,dict):raise RichMessageInvalid('typed rich text required')
        kind=node.get('type')
        if kind=='url' and set(node)=={'type','text','url'}:
            _url(node['url'],source_urls);text(node['text'],depth+1)
        elif kind=='reference' and set(node)=={'type','text','name'}:
            if not isinstance(node['name'],str) or not re.fullmatch(r'[a-zA-Z0-9_]{1,128}',node['name']):raise RichMessageInvalid('bounded source reference name required')
            if node['name'] in references:raise RichMessageInvalid('duplicate rich reference')
            references.add(node['name']);text(node['text'],depth+1)
        elif kind in {'bold','italic','code'} and set(node)=={'type','text'}:text(node['text'],depth+1)
        else:raise RichMessageInvalid('unsupported executable rich text')
    def blocks(nodes,depth):
        nonlocal count
        if depth>MAX_DEPTH or not isinstance(nodes,list):raise RichMessageInvalid('nested rich block bound')
        for node in nodes:
            count+=1
            if not isinstance(node,dict):raise RichMessageInvalid('typed rich block required')
            kind=node.get('type')
            if kind in {'paragraph','footer'} and set(node)=={'type','text'}:text(node['text'],depth+1)
            elif kind=='heading' and set(node)=={'type','text','size'}:
                if type(node['size'])is not int or not 1<=node['size']<=6:raise RichMessageInvalid('invalid heading size')
                text(node['text'],depth+1)
            elif kind=='details' and set(node)<= {'type','summary','blocks','is_open'} and {'summary','blocks'}<=set(node):
                if 'is_open' in node and node['is_open']is not True:raise RichMessageInvalid('invalid details flag')
                text(node['summary'],depth+1);blocks(node['blocks'],depth+1)
            elif kind=='table' and set(node)<= {'type','cells','is_compact','is_bordered','is_striped','caption'} and 'cells' in node:
                rows=node['cells']
                if not isinstance(rows,list) or not rows:raise RichMessageInvalid('bounded table rows required')
                for key in ('is_compact','is_bordered','is_striped'):
                    if key in node and node[key]is not True:raise RichMessageInvalid('invalid table flag')
                for row in rows:
                    count+=1
                    if not isinstance(row,list) or not 1<=len(row)<=MAX_COLUMNS:raise RichMessageInvalid('table width exceeds bound')
                    columns=0
                    for cell in row:
                        if not isinstance(cell,dict) or not {'text','align'}<=set(cell) or set(cell)-{'text','align','valign','is_header','colspan','rowspan'}:raise RichMessageInvalid('typed table cell required')
                        if cell['align'] not in {'left','center','right'} or cell.get('valign','top') not in {'top','middle','bottom'}:raise RichMessageInvalid('invalid table alignment')
                        for span in ('colspan','rowspan'):
                            if span in cell and (type(cell[span])is not int or not 1<=cell[span]<=MAX_COLUMNS):raise RichMessageInvalid('invalid table span')
                        if 'is_header' in cell and cell['is_header']is not True:raise RichMessageInvalid('invalid table header')
                        columns+=cell.get('colspan',1);text(cell['text'],depth+1)
                    if columns>MAX_COLUMNS:raise RichMessageInvalid('table span exceeds width')
                if 'caption' in node:text(node['caption'],depth+1)
            elif kind=='buttons' and set(node)=={'type','buttons'}:
                buttons=node['buttons']
                if not isinstance(buttons,list) or not 1<=len(buttons)<=8:raise RichMessageInvalid('bounded trusted buttons required')
                for button in buttons:
                    if (not isinstance(button,dict) or set(button)!={'text','callback_data'} or not isinstance(button['text'],str)
                        or not 1<=len(button['text'])<=90 or button['callback_data'] not in callback_tokens
                        or not re.fullmatch(r'paic:[a-f0-9]{32}',button['callback_data'])):raise RichMessageInvalid('untrusted callback button')
                    text(button['text'],depth+1)
            else:raise RichMessageInvalid('unsupported rich block or media')
    blocks(value['blocks'],1)
    if characters>maximum_characters or count>MAX_BLOCKS:raise RichMessageInvalid('rich text/block bound exceeded')
    return {'characters':characters,'blocks':count,'media':0,'source_refs':len(references)}


def plain_text(value):
    """Comparable lossless text projection; source URLs remain visible pointers."""
    def text(node):
        if isinstance(node,str):return node
        if isinstance(node,list):return ''.join(text(n) for n in node)
        value=text(node['text'])
        return value+' ('+node['url']+')' if node.get('type')=='url' else value
    lines=[]
    def walk(nodes):
        for block in nodes:
            if 'text' in block:lines.append(text(block['text']))
            if block['type']=='details':lines.append(text(block['summary']));walk(block['blocks'])
            if block['type']=='table':
                for row in block['cells']:lines.append(' | '.join(text(c['text']) for c in row))
            if block['type']=='buttons':lines.append(' · '.join(b['text'] for b in block['buttons']))
    walk(value['blocks']);return '\n'.join(lines)


def _message(blocks):return {'blocks':blocks,'skip_entity_detection':True}


def _split(blocks,*,source_urls,callback_tokens,maximum_characters):
    def fits(nodes):
        try:
            validate_rich_message(_message(nodes),source_urls=source_urls,callback_tokens=callback_tokens,maximum_characters=maximum_characters)
            return len(json.dumps(_message(nodes),ensure_ascii=False).encode())<=24000
        except RichMessageInvalid:return False
    def atoms(block):
        if fits([block]):return [block]
        if block.get('type')=='paragraph' and isinstance(block.get('text'),str):
            chunks=[];part='';size=0
            for char in block['text']:
                extra=len(json.dumps(char,ensure_ascii=False).encode())-2
                if part and (len(part)>=maximum_characters or size+extra>22000):chunks.append({'type':'paragraph','text':part});part='';size=0
                part+=char;size+=extra
            if part:chunks.append({'type':'paragraph','text':part})
            return chunks
        if block.get('type')=='details':
            children=[part for child in block['blocks'] for part in atoms(child)];out=[];current=[]
            for child in children:
                candidate={**block,'blocks':current+[child]}
                if current and not fits([candidate]):out.append({**block,'blocks':current});current=[]
                current.append(child)
                if not fits([{**block,'blocks':current}]):
                    # Oversized leaf text is split with the details heading budget.
                    if child.get('type')!='paragraph' or not isinstance(child.get('text'),str):raise RichMessageInvalid('one section exceeds rich bound')
                    size=maximum_characters-len(str(block['summary']))
                    if size<64:raise RichMessageInvalid('details heading exceeds budget')
                    for i in range(0,len(child['text']),size):out.append({**block,'blocks':[{'type':'paragraph','text':child['text'][i:i+size]}]})
                    current=[]
            if current:out.append({**block,'blocks':current})
            return out
        if block.get('type')=='table':
            out=[];current=[]
            for row in block['cells']:
                if current and not fits([{**block,'cells':current+[row]}]):out.append({**block,'cells':current});current=[]
                current.append(row)
                if not fits([{**block,'cells':current}]):raise RichMessageInvalid('one table row exceeds rich bound')
            if current:out.append({**block,'cells':current})
            return out
        raise RichMessageInvalid('unsupported or oversized rich section')
    pieces=[piece for block in blocks for piece in atoms(block)];parts=[];current=[]
    for piece in pieces:
        if current and not fits(current+[piece]):parts.append(_message(current));current=[]
        if not fits([piece]):raise RichMessageInvalid('single rich section exceeds bound')
        current.append(piece)
    if current:parts.append(_message(current))
    if not 1<=len(parts)<=32:raise RichMessageInvalid('bounded rich parts required')
    return tuple(parts)


@dataclass(frozen=True)
class RichReport:
    brief_id:str
    version:int
    content_digest:str
    source_refs:tuple[str,...]
    messages:tuple[dict,...]
    renderer_version:str='telegram-rich-v1'


def render_rich_brief(document,*,controls=(),maximum_characters=MAX_CHARACTERS,view='full',story_number=None):
    if type(document)is not BriefDocument:raise RichMessageInvalid('immutable BriefDocument required')
    sources=tuple(dict.fromkeys(e.source_ref for e in document.evidence));tokens=tuple(b['callback_data'] for b in controls)
    blocks=[{'type':'heading','text':document.topic,'size':1},{'type':'paragraph','text':document.window.start_at.date().isoformat()+' — '+document.window.end_at.date().isoformat()+' · '+document.window.timezone}]
    stories=document.editorial.stories if document.editorial else ()
    if story_number is not None and view in {'item','why','simplify','next_step','sources','caveat'}:
        if type(story_number)is not int or not 1<=story_number<=len(stories):raise RichMessageInvalid('exact rich story unavailable')
        stories=stories[story_number-1:story_number]
    for story in stories:
        blocks.append({'type':'heading','text':story.title,'size':2})
        wording={'why':(story.why_selected,story.caveat),'simplify':(story.plain_explanation,story.caveat),'next_step':(story.next_step,story.caveat),
            'caveat':(story.caveat,),'sources':(), 'short':(story.summary,story.caveat)}.get(view,(story.summary,story.explanation,story.plain_explanation,story.why_selected,story.next_step,story.caveat))
        for text in dict.fromkeys(wording):
            if text:blocks.append({'type':'paragraph','text':text})
        anchors=[]
        for anchor in story.anchors:
            evidence=document.evidence_by_ref()[anchor.evidence_ref]
            anchors.extend([{'type':'paragraph','text':{'type':'url','text':evidence.title,'url':evidence.source_ref}}, {'type':'paragraph','text':anchor.quote}])
        if anchors:blocks.append({'type':'details','summary':'Основания и источники','blocks':anchors})
    if not stories:
        for item in document.items:blocks.extend([{'type':'heading','text':item.title,'size':2},{'type':'paragraph','text':item.summary}])
    source_blocks=[]
    for index,evidence in enumerate(document.evidence):
        source_blocks.extend([{'type':'paragraph','text':{'type':'reference','name':'source_'+str(index+1),'text':{'type':'url','text':evidence.title,'url':evidence.source_ref}}},
            {'type':'paragraph','text':evidence.summary}])
    if source_blocks:blocks.append({'type':'details','summary':'Все материалы сохранённой версии','blocks':source_blocks})
    from prm.report_exports import _coverage_source_name,_coverage_state_name,_limitation_name
    cells=[[{'text':'Источник','align':'left','is_header':True},{'text':'Покрытие','align':'left','is_header':True}]]
    cells.extend([{'text':_coverage_source_name(s.source_ref),'align':'left'},{'text':_coverage_state_name(s.state),'align':'left'}] for s in document.coverage_manifest.sources)
    if len(cells)>1:blocks.append({'type':'table','cells':cells,'is_compact':True})
    for limitation in document.coverage_manifest.limitations:blocks.append({'type':'paragraph','text':_limitation_name(limitation)})
    if document.status=='empty':blocks.append({'type':'paragraph','text':'В проверенной выборке важных изменений не найдено.'})
    blocks.append({'type':'footer','text':'Версия '+str(document.version)+'. Отображение сохранённого документа; применение и полезность не измерены.'})
    if controls:blocks.append({'type':'buttons','buttons':[dict(b) for b in controls]})
    messages=_split(blocks,source_urls=sources,callback_tokens=tokens,maximum_characters=maximum_characters)
    return RichReport(document.brief_id,document.version,document.content_digest,sources,messages)


def render_rich_answer(text,*,maximum_characters=MAX_CHARACTERS):
    if not isinstance(text,str) or not text or len(text)>128000:raise RichMessageInvalid('bounded immutable answer text required')
    return _split([{'type':'paragraph','text':text}],source_urls=(),callback_tokens=(),maximum_characters=maximum_characters)
