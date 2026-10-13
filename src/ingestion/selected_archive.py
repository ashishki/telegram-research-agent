"""Explicit bounded source observations; canonical posts and cursor commit together."""
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
import sqlite3,hashlib,json,re
from prm.storage.postgres import StorageError,StateConflict
from prm.runtime.profiles import aware


@dataclass(frozen=True)
class ArchiveSelection:
    owner_ref: str
    resource_ref: str
    version: int
    channels: tuple[tuple[int,str],...]
    mode: str = 'import'
    page_limit: int = 200
    daily_quota: int = 1000
    max_lag_seconds: int = 86400

    def __post_init__(self):
        if not isinstance(self.owner_ref,str) or not self.owner_ref.startswith('owner_') or not isinstance(self.resource_ref,str) or not self.resource_ref.startswith('resource_') or type(self.version)is not int or self.version<1:raise StorageError('owner/versioned source selection required')
        if not isinstance(self.channels,tuple) or not 1<=len(self.channels)<=32 or len({p[0] for p in self.channels})!=len(self.channels) or len({p[1] for p in self.channels})!=len(self.channels):raise StorageError('bounded unique source channel identities required')
        for channel_id,username in self.channels:
            if type(channel_id)is not int or channel_id<=0 or not isinstance(username,str) or not re.fullmatch('@[a-z][a-z0-9_]{3,31}',username):raise StorageError('normalized selected channel required')
        if self.mode not in {'import','forward','session'} or type(self.page_limit)is not int or not 1<=self.page_limit<=200 or type(self.daily_quota)is not int or not 1<=self.daily_quota<=10000 or type(self.max_lag_seconds)is not int or not 1<=self.max_lag_seconds<=604800:raise StorageError('bounded source mode/quota/lag required')
    @property
    def digest(self):return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()


def install_selected_archive(conn):
    """Explicit local installation. Never called by startup, collector or reader."""
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS pa_archive_selection(owner TEXT NOT NULL,resource TEXT NOT NULL,version INTEGER NOT NULL,digest TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,cursor TEXT,checked_at TEXT,watermark TEXT,outcome TEXT NOT NULL DEFAULT 'never_checked',PRIMARY KEY(owner,resource));
      CREATE TABLE IF NOT EXISTS pa_archive_pages(owner TEXT NOT NULL,resource TEXT NOT NULL,page_id TEXT NOT NULL,digest TEXT NOT NULL,receipt TEXT NOT NULL,PRIMARY KEY(owner,resource,page_id));
      CREATE TABLE IF NOT EXISTS pa_archive_revisions(owner TEXT NOT NULL,resource TEXT NOT NULL,channel_id INTEGER NOT NULL,message_id INTEGER NOT NULL,revision INTEGER NOT NULL,digest TEXT NOT NULL,deleted INTEGER NOT NULL,PRIMARY KEY(owner,resource,channel_id,message_id));
      CREATE TABLE IF NOT EXISTS pa_archive_quota(owner TEXT NOT NULL,resource TEXT NOT NULL,day TEXT NOT NULL,used INTEGER NOT NULL,PRIMARY KEY(owner,resource,day));
    ''')


class SelectedArchive:
    def __init__(self,conn,selection):self.conn,self.selection=conn,selection
    def register(self):
        s=self.selection
        with self.conn:
            if self.conn.execute('SELECT 1 FROM pa_archive_selection WHERE owner<>? LIMIT 1',(s.owner_ref,)).fetchone():raise StorageError('canonical archive already belongs to another owner')
            for channel_id,username in s.channels:
                if self.conn.execute('SELECT 1 FROM raw_posts WHERE channel_id=? AND channel_username<>? LIMIT 1',(channel_id,username)).fetchone():raise StorageError('canonical source channel identity differs')
            old=self.conn.execute('SELECT version,digest FROM pa_archive_selection WHERE owner=? AND resource=?',(s.owner_ref,s.resource_ref)).fetchone()
            if old:
                if tuple(old)!=(s.version,s.digest):raise StateConflict('selected archive config changed; explicit new version installation required')
                return
            self.conn.execute('INSERT INTO pa_archive_selection(owner,resource,version,digest) VALUES(?,?,?,?)',(s.owner_ref,s.resource_ref,s.version,s.digest))
    def current(self):
        s=self.selection
        row=self.conn.execute('SELECT version,digest,active,cursor,checked_at,watermark,outcome FROM pa_archive_selection WHERE owner=? AND resource=?',(s.owner_ref,s.resource_ref)).fetchone()
        if not row or row[0]!=s.version or row[1]!=s.digest or not row[2]:raise StorageError('selected source unavailable or changed')
        return {'version':row[0],'scope_digest':row[1],'cursor':row[3],'checked_at':row[4],'watermark':row[5],'outcome':row[6]}
    def pause(self):
        s=self.selection
        with self.conn:self.conn.execute('UPDATE pa_archive_selection SET active=0 WHERE owner=? AND resource=? AND digest=?',(s.owner_ref,s.resource_ref,s.digest))
    def outage(self):
        self.current();s=self.selection
        with self.conn:self.conn.execute("UPDATE pa_archive_selection SET outcome='unavailable' WHERE owner=? AND resource=?",(s.owner_ref,s.resource_ref))
    def status(self,now=None):
        state=self.current();now=aware(now or datetime.now(timezone.utc))
        lag=max(0,int((now-aware(state['watermark'])).total_seconds())) if state['watermark'] else None
        fresh=lag is not None and lag<=self.selection.max_lag_seconds and state['outcome']=='complete' and self.selection.mode=='session'
        return {**state,'mode':self.selection.mode,'selected_channels':[p[1] for p in self.selection.channels],'lag_seconds':lag,'fresh':fresh,'history_complete':False,'selected_scan_complete':fresh,
            'limitation':None if fresh else 'selected_import_or_forward_is_not_full_history' if self.selection.mode!='session' else 'incomplete_or_stale_enumeration'}
    def apply_page(self,*,page_id,expected_cursor,next_cursor,events,watermark,complete=False,checked_at=None):
        s=self.selection;checked_at=aware(checked_at or datetime.now(timezone.utc));watermark=aware(watermark)
        if checked_at>datetime.now(timezone.utc)+__import__('datetime').timedelta(seconds=5) or watermark>checked_at:raise StorageError('observation time cannot be invented in future')
        if not isinstance(page_id,str) or not 0<len(page_id)<=128 or any(x is not None and (not isinstance(x,str) or len(x)>256) for x in (expected_cursor,next_cursor)) or type(complete)is not bool or complete and next_cursor is not None:raise StorageError('bounded exact observation cursor required')
        if not isinstance(events,list) or len(events)>s.page_limit:raise StorageError('source page exceeds selected quota')
        channels=dict(s.channels)
        for e in events:
            if not isinstance(e,dict) or set(e)!={'channel_id','message_id','revision','posted_at','text','deleted'} or type(e['channel_id'])is not int or e['channel_id'] not in channels or type(e['message_id'])is not int or e['message_id']<=0 or type(e['revision'])is not int or e['revision']<0 or type(e['deleted'])is not bool or not isinstance(e['text'],str) or len(e['text'].encode())>65536 or e['deleted'] and e['text']:raise StorageError('bounded selected source observation required')
            if e['posted_at'] is None and not e['deleted']:raise StorageError('publication date required for live post')
            if e['posted_at'] is not None and aware(e['posted_at'])>watermark:raise StorageError('post outside observed watermark')
        packet={'page_id':page_id,'expected_cursor':expected_cursor,'next_cursor':next_cursor,'events':events,'watermark':watermark.isoformat(),'complete':complete,'scope':s.digest}
        digest=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
        if self.conn.in_transaction:raise StorageError('source page needs its own atomic canonical transaction')
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            state=self.current()
            old=self.conn.execute('SELECT digest,receipt FROM pa_archive_pages WHERE owner=? AND resource=? AND page_id=?',(s.owner_ref,s.resource_ref,page_id)).fetchone()
            if old:
                if old[0]!=digest:raise StateConflict('source page identity changed')
                self.conn.rollback();return json.loads(old[1])
            if state['cursor']!=expected_cursor:raise StateConflict('source cursor changed or page interrupted')
            if state['watermark'] and watermark<aware(state['watermark']):raise StateConflict('source watermark cannot move backwards')
            day=checked_at.astimezone(timezone.utc).date().isoformat();quota=self.conn.execute('SELECT used FROM pa_archive_quota WHERE owner=? AND resource=? AND day=?',(s.owner_ref,s.resource_ref,day)).fetchone()
            if (quota[0] if quota else 0)+len(events)>s.daily_quota:raise StorageError('selected source daily quota exhausted')
            changed=0
            for e in events:
                key=(s.owner_ref,s.resource_ref,e['channel_id'],e['message_id'])
                hashed=hashlib.sha256(json.dumps(e,sort_keys=True).encode()).hexdigest()
                previous=self.conn.execute('SELECT revision,digest FROM pa_archive_revisions WHERE owner=? AND resource=? AND channel_id=? AND message_id=?',key).fetchone()
                if previous:
                    if previous[0]>e['revision']:continue
                    if previous[0]==e['revision']:
                        if previous[1]!=hashed:raise StateConflict('same source revision conflicts')
                        continue
                raw=self.conn.execute('SELECT id,posted_at FROM raw_posts WHERE channel_id=? AND message_id=?',(e['channel_id'],e['message_id'])).fetchone()
                posted=aware(e['posted_at']).isoformat() if e['posted_at'] is not None else raw[1] if raw else ''
                if not raw:
                    from ingestion.bootstrap_ingest import _insert_message
                    row={'channel_username':channels[e['channel_id']],'channel_id':e['channel_id'],'message_id':e['message_id'],'posted_at':posted,'text':e['text'],'media_type':'none','media_caption':None,'forward_from':None,'view_count':0,'message_url':'https://t.me/'+channels[e['channel_id']].lstrip('@')+'/'+str(e['message_id']),'raw_json':'{}','ingested_at':checked_at.isoformat()}
                    _insert_message(self.conn.cursor(),row)
                    raw=self.conn.execute('SELECT id,posted_at FROM raw_posts WHERE channel_id=? AND message_id=?',(e['channel_id'],e['message_id'])).fetchone()
                text=None if e['deleted'] else e['text'];raw_json=json.dumps({'revision':e['revision'],'deleted':e['deleted']})
                self.conn.execute('UPDATE raw_posts SET text=?,media_caption=NULL,image_description=NULL,raw_json=?,posted_at=?,ingested_at=? WHERE id=?',(text,raw_json,posted,checked_at.isoformat(),raw[0]))
                from processing.normalize_posts import _clean_content,_extract_metadata,_detect_language
                content=_clean_content(text);urls,code,words=_extract_metadata(content)
                self.conn.execute('INSERT INTO posts(raw_post_id,channel_username,posted_at,content,url_count,has_code,language_detected,word_count,normalized_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(raw_post_id) DO UPDATE SET posted_at=excluded.posted_at,content=excluded.content,url_count=excluded.url_count,has_code=excluded.has_code,language_detected=excluded.language_detected,word_count=excluded.word_count,normalized_at=excluded.normalized_at',(raw[0],channels[e['channel_id']],posted,content,urls,code,_detect_language(content),words,checked_at.isoformat()))
                self.conn.execute('INSERT INTO pa_archive_revisions VALUES(?,?,?,?,?,?,?) ON CONFLICT(owner,resource,channel_id,message_id) DO UPDATE SET revision=excluded.revision,digest=excluded.digest,deleted=excluded.deleted',(*key,e['revision'],hashed,int(e['deleted'])));changed+=1
            self.conn.execute('INSERT INTO pa_archive_quota VALUES(?,?,?,?) ON CONFLICT(owner,resource,day) DO UPDATE SET used=used+excluded.used',(s.owner_ref,s.resource_ref,day,len(events)))
            outcome='complete' if complete else 'partial'
            self.conn.execute('UPDATE pa_archive_selection SET cursor=?,checked_at=?,watermark=?,outcome=? WHERE owner=? AND resource=?',(next_cursor,checked_at.isoformat(),watermark.isoformat(),outcome,s.owner_ref,s.resource_ref))
            receipt={'page_id':page_id,'changed':changed,'received':len(events),'cursor':next_cursor,'outcome':outcome,'scope_digest':s.digest,'mode':s.mode}
            self.conn.execute('INSERT INTO pa_archive_pages VALUES(?,?,?,?,?)',(s.owner_ref,s.resource_ref,page_id,digest,json.dumps(receipt,sort_keys=True)))
            self.conn.commit();return receipt
        except Exception:self.conn.rollback();raise


def source_file_lock(path,*,exclusive=False):
    """Cooperating readers/writers keep source pause/edit ordered across WAL snapshots."""
    from contextlib import contextmanager
    @contextmanager
    def held():
        import fcntl,time
        if not path:yield;return
        with open(path,'rb') as file:
            deadline=time.monotonic()+2
            while True:
                try:fcntl.flock(file.fileno(),(fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if time.monotonic()>=deadline:raise StorageError('selected source lock unavailable')
                    time.sleep(.01)
            try:yield
            finally:fcntl.flock(file.fileno(),fcntl.LOCK_UN)
    return held()


def _ordered(method):
    from functools import wraps
    @wraps(method)
    def run(self,*args,**kwargs):
        path=self.conn.execute('PRAGMA database_list').fetchone()[2]
        with source_file_lock(path,exclusive=True):return method(self,*args,**kwargs)
    return run

for _method in ('register','pause','outage','apply_page'):
    setattr(SelectedArchive,_method,_ordered(getattr(SelectedArchive,_method)))


class TelegramSelectedCollector:
    """One selected channel/window page from an already authorized existing client.

    Page cursor binds channel, offset and selection. Bounded known-ID refresh
    observes edits/deletes separately; neither mode attests all Telegram history.
    """
    def __init__(self,client):self.client=client
    async def fetch_page(self,selection,*,cursor=None,known_ids=()):
        if selection.mode!='session':raise StorageError('session collector requires its selected route')
        index=0;offset=0
        if cursor:
            try:scope,index,offset=cursor.split(':');index=int(index);offset=int(offset)
            except (ValueError,AttributeError):raise StorageError('invalid selected collector cursor') from None
            if scope!=selection.digest or not 0<=index<len(selection.channels) or offset<0:raise StorageError('selected collector cursor scope differs')
        channel_id,username=selection.channels[index];entity=await self.client.get_entity(username)
        if getattr(entity,'id',None)!=channel_id:raise StorageError('selected Telegram channel differs')
        now=datetime.now(timezone.utc);events=[]
        if known_ids:
            if not isinstance(known_ids,tuple) or len(known_ids)>selection.page_limit or any(type(i)is not int or i<=0 for i in known_ids):raise StorageError('bounded selected message refresh required')
            messages=await self.client.get_messages(entity,ids=list(known_ids))
            if not isinstance(messages,(list,tuple)) or len(messages)!=len(known_ids):raise StorageError('message refresh shape differs')
            pairs=zip(known_ids,messages);next_cursor=cursor;complete=False
        else:
            messages=[]
            async for message in self.client.iter_messages(entity,offset_id=offset,limit=selection.page_limit+1):
                messages.append(message)
                if len(messages)>selection.page_limit:break
            more=len(messages)>selection.page_limit;messages=messages[:selection.page_limit]
            if more:next_cursor=selection.digest+':'+str(index)+':'+str(messages[-1].id)
            elif index+1<len(selection.channels):next_cursor=selection.digest+':'+str(index+1)+':0'
            else:next_cursor=None
            pairs=((m.id,m) for m in messages);complete=next_cursor is None
        for identity,message in pairs:
            deleted=message is None or getattr(message,'date',None) is None
            if not deleted and (message.id!=identity or getattr(getattr(message,'peer_id',None),'channel_id',None)!=channel_id):raise StorageError('selected message identity differs')
            posted=None if deleted else aware(message.date)
            revision=int((now if deleted else aware(getattr(message,'edit_date',None) or message.date)).timestamp()*1000000)
            if deleted:text=''
            else:
                from ingestion.bootstrap_ingest import _extract_message_row
                text=_extract_message_row(message,username,now.isoformat())['text']
            events.append({'channel_id':channel_id,'message_id':identity,'revision':revision,'posted_at':posted.isoformat() if posted else None,'text':text,'deleted':deleted})
        page_id=hashlib.sha256(json.dumps([selection.digest,cursor,events],sort_keys=True).encode()).hexdigest()
        return {'page_id':page_id,'expected_cursor':cursor,'next_cursor':next_cursor,'events':events,'watermark':now.isoformat(),'checked_at':now.isoformat(),'complete':complete}
