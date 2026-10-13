"""Frozen synthetic retrieval labels and canonical sidecar fences."""
import json,hashlib,sqlite3
from pathlib import Path
from tests.test_archive_search import _make_connection,_insert_post
from db.archive_retrieval import retrieve_archive,query_variants
from db.archive_vector import build_archive_vector_index

FIXTURE=Path('evals/retrieval/daily-20261013.json')

def corpus():
    conn=_make_connection()
    value=json.loads(FIXTURE.read_text())
    for item in value['corpus']:
        _insert_post(conn,post_id=item['id'],channel_id=item['channel_id'],channel_username=item['channel_username'],
            language=item['language'],posted_at='2026-10-12T12:00:00Z',content=item['text'])
    conn.commit();return conn,value

def test_frozen_retrieval_exact_bilingual_and_no_answer(tmp_path):
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()=='dca963beb017300facc1d956c4bd057f738b80199057caaa9326ffdedc09984c'
    conn,value=corpus()
    try:
        assert any(i.post_id==1 for i in retrieve_archive(conn,'Оценка агентов',limit=20).items)
        assert any(i.post_id==2 for i in retrieve_archive(conn,'agent evaluation',limit=20).items)
        for case in value['cases']:
            items=retrieve_archive(conn,case['query'],filters=case['filters'],limit=20).items
            if not case['relevance']:assert items==()
            if case['category']=='filter':assert {str(i.post_id) for i in items}<=set(case['relevance'])
        assert len(query_variants('Оценка агентов'))<=3
    finally:conn.close()

def test_sidecar_cannot_resurrect_deleted_revised_or_unselected_candidates(tmp_path):
    conn,_=corpus();path=tmp_path/'derived.sqlite'
    try:
        build_archive_vector_index(conn,index_path=path)
        conn.execute("UPDATE posts SET content='Changed canonical source' WHERE id=3")
        conn.execute("DELETE FROM posts WHERE id=4")
        conn.commit()
        result=retrieve_archive(conn,'retrieval vector',limit=20,vector_index_path=path,
            filters={'channel_identities':((1001,'@alpha'),)})
        assert all(i.post_id not in (3,4) and i.channel_id==1001 for i in result.items)
        assert result.rejected_sidecar_count>=1
    finally:conn.close()

def test_shared_service_deduplicates_content_and_obeys_project_filter():
    conn,_=corpus()
    try:
        conn.execute("INSERT INTO projects(id,name,description,keywords) VALUES(1,'Synthetic','','')")
        conn.execute("INSERT INTO post_project_links VALUES(1,1,1.0,'Synthetic')")
        result=retrieve_archive(conn,'agent evaluation',filters={'project_names':['Synthetic']},limit=20)
        assert [i.post_id for i in result.items]==[1]
        result=retrieve_archive(conn,'agent evaluation',limit=20)
        assert len({i.content_hash for i in result.items})==len(result.items)
    finally:conn.close()

def test_exact_canonical_id_and_source_url_still_obey_selection_filters():
    conn,_=corpus()
    try:
        assert [i.post_id for i in retrieve_archive(conn,'tg:1001:1001',limit=20).items]==[1]
        assert [i.post_id for i in retrieve_archive(conn,'https://t.me/alpha/1001',limit=20).items]==[1]
        assert not retrieve_archive(conn,'tg:1001:1001',filters={'channel_identities':((1002,'@beta'),)},limit=20).items
    finally:conn.close()

def test_compatibility_hybrid_revalidates_canonical_before_returning_sidecar(tmp_path):
    from db.archive_vector import search_telegram_archive_hybrid
    conn,_=corpus();path=tmp_path/'old-hybrid.sqlite'
    try:
        build_archive_vector_index(conn,index_path=path)
        conn.execute("UPDATE posts SET content='Changed canonical source' WHERE id=3")
        conn.execute('DELETE FROM posts WHERE id=4');conn.commit()
        result=search_telegram_archive_hybrid(conn,'retrieval vector',vector_index_path=path,limit=20,
            filters={'channel_identities':((1001,'@alpha'),)})
        assert all(i.post_id not in (3,4) and i.channel_id==1001 for i in result)
    finally:conn.close()

def test_pi_facade_hybrid_keeps_exact_identity_and_current_project_membership(tmp_path):
    from assistant.pi_facade import PersonalIntelligenceFacade
    from config.settings import Settings
    conn,_=corpus();index=tmp_path/'derived.sqlite';path=tmp_path/'canonical.sqlite'
    conn.execute("INSERT INTO projects(id,name,description,keywords) VALUES(1,'Synthetic','','')")
    conn.execute("INSERT INTO post_project_links VALUES(3,1,1.0,'Synthetic')");conn.commit()
    build_archive_vector_index(conn,index_path=index)
    conn.execute('DELETE FROM post_project_links');conn.commit()
    with sqlite3.connect(path) as saved:conn.backup(saved)
    conn.close()
    facade=PersonalIntelligenceFacade(settings=Settings(db_path=str(path),llm_api_key='',model_provider='synthetic',telegram_session_path=str(tmp_path/'unused.session')))
    result=facade.search_telegram_archive('retrieval vector',filters={'retrieval_mode':'hybrid','vector_index_path':str(index),'vector_policy':'always',
        'channel_identities':((1001,'@alpha'),),'project_names':['Synthetic']})
    assert not result['items']
    result=facade.search_telegram_archive('retrieval vector',filters={'retrieval_mode':'hybrid','vector_index_path':str(index),'vector_policy':'always','channel_identities':((1001,'@alpha'),)})
    assert result['items'] and all(i['channel_id']==1001 for i in result['items'])

from tests.pai_runtime_fixtures import pai,allow

def test_native_retrieval_cache_binds_every_filter_not_only_query(pai):
    from prm.runtime.research import LocalArchiveReader
    conn,_=corpus();path=pai.path/'cache-scope.sqlite'
    with sqlite3.connect(path) as saved:conn.backup(saved)
    conn.close()
    allow(pai,'archive.read',pai.root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    reader=LocalArchiveReader(path,root=pai.root)
    english=reader.search_archive('agent evaluation',limit=8,filters={'languages':['en']})
    russian=reader.search_archive('agent evaluation',limit=8,filters={'languages':['ru']})
    assert english['items'] and russian['items']
    assert all(i['language']=='en' for i in english['items']) and all(i['language']=='ru' for i in russian['items'])
    assert russian['retrieval']['version']=='canonical-retrieval-v1'
