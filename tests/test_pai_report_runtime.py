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
            assert 'brief-report--designed' in html and 'kpis' in html
        pdf,kind=reader.artifact(token,brief_id=document.brief_id,version=document.version,format='pdf')
        assert pdf.startswith(b'%PDF-') and kind=='application/pdf'
        reader.revoke(token)
        assert reader.artifact(token,brief_id=document.brief_id,version=document.version,format='html') is None
    finally:server.shutdown();thread.join(timeout=5);server.server_close()


def test_private_pdf_uses_native_renderer_inside_network_block(pai):
    from io import BytesIO
    from pypdf import PdfReader
    document,state=stored_brief(pai)
    reader=PrivateReportRuntime(pai.root,artifact_root=pai.path/'native_artifacts')
    token=reader.issue_session(chat_id='42',actor_id='42',owner_chat_id='42')
    body,_=reader.artifact(token,brief_id=document.brief_id,version=document.version,format='pdf')
    parsed=PdfReader(BytesIO(body))
    assert str(parsed.metadata.get('/Producer','')).startswith('WeasyPrint')
    assert 'Важное событие' in ''.join(page.extract_text() or '' for page in parsed.pages)


def test_network_block_keeps_ssl_importable_and_rejects_socket_io():
    import subprocess,sys
    result=subprocess.run([sys.executable,'-c',
        'from prm.runtime.network_guard import install_network_block; install_network_block(); import ssl,socket; socket.create_connection(("127.0.0.1",1))'],
        capture_output=True,text=True,timeout=5)
    assert result.returncode!=0 and 'isolated processor network disabled' in result.stderr
    assert 'TypeError' not in result.stderr
