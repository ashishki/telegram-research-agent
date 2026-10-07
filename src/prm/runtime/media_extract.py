"""Network-free bounded PDF/image extraction subprocess."""
import argparse
import json
from pathlib import Path
import resource
import socket


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--output',required=True);parser.add_argument('--mime',required=True)
    args=parser.parse_args(argv)
    resource.setrlimit(resource.RLIMIT_CPU,(8,8));resource.setrlimit(resource.RLIMIT_AS,(1000000000,1000000000));resource.setrlimit(resource.RLIMIT_FSIZE,(64000,64000))
    from .network_guard import install_network_block
    install_network_block()
    path=Path(args.input)
    if path.stat().st_size>16000000:raise ValueError('media exceeds bound')
    pages=[]
    if args.mime=='application/pdf':
        from pypdf import PdfReader
        reader=PdfReader(path)
        root=reader.trailer['/Root']
        if reader.is_encrypted or '/OpenAction' in root or '/AA' in root or '/EmbeddedFiles' in root.get('/Names',{}):raise ValueError('active/encrypted PDF denied')
        if len(reader.pages)>32:raise ValueError('PDF page bound exceeded')
        for index,page in enumerate(reader.pages):
            if '/AA' in page:raise ValueError('active PDF page denied')
            pages.append([index+1,(page.extract_text() or '')[:8000]])
        if sum(len(text) for page,text in pages)>48000:raise ValueError('extracted text exceeds bound')
    elif args.mime in {'image/png','image/jpeg'}:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS=20000000
        with Image.open(path) as image:
            if image.width*image.height>20000000:raise ValueError('image dimensions exceed bound')
            image.verify()
        pages=[[1,'']]
    else:raise ValueError('unsupported extraction MIME')
    Path(args.output).write_text(json.dumps({'status':'extracted','method':'text_layer','pages':pages},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
