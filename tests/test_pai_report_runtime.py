"""Deferred actual subprocess and authenticated HTTP report checks."""
from threading import Thread
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import pytest
from tests.pai_runtime_fixtures import pai
from tests.test_pai_brief_runtime import stored_brief
from prm.runtime.reader import PrivateReportRuntime


def test_actual_reader_subprocess_versions_and_private_http_headers(pai):
    document,state=stored_brief(pai)
    reader=PrivateReportRuntime(pai.root,artifact_root=pai.path/'artifacts')
    token=reader.issue_session(chat_id='42',actor_id='42',owner_chat_id='42')
    server=reader.server();thread=Thread(target=server.serve_forever);thread.start()
    url=f'http://127.0.0.1:{server.server_port}/report/{document.brief_id}/{document.version}/html'
    try:
        with pytest.raises(HTTPError):urlopen(url)
        with urlopen(Request(url,headers={'Authorization':'Bearer '+token})) as response:
            html=response.read().decode();assert 'noindex' in response.headers['X-Robots-Tag']
            assert document.content_digest in html and 'Важное событие' in html
        pdf,kind=reader.artifact(token,brief_id=document.brief_id,version=document.version,format='pdf')
        assert pdf.startswith(b'%PDF-') and kind=='application/pdf'
        reader.revoke(token)
        assert reader.artifact(token,brief_id=document.brief_id,version=document.version,format='html') is None
    finally:server.shutdown();thread.join(timeout=5);server.server_close()
