"""Exercise handler/admission/lifecycle without creating a socket or browser."""
import copy,io,json,os,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import serve
import human_voice_review as review


class PreviewBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=Path(os.environ['TEST_TMP_ROOT'])/'static-preview'
        cls.temp.mkdir(parents=True)
        os.environ['CONTENT_STUDIO_REVIEW_WORKSPACE']=str(cls.temp)
        bundle=review.build_bundle(json.loads((ROOT/'fixtures/minimal-review/request.json').read_text()),ROOT)
        cls.site=cls.temp/'site';review.build_page(bundle,cls.site,ROOT)
        (cls.site/'private.txt').write_text('SYNTHETIC EXCLUDED CONTENT',encoding='utf-8')
        (cls.site/'nested').mkdir()
        (cls.site/'nested/index.html').write_text('SYNTHETIC EXCLUDED',encoding='utf-8')

    def handler(self,path='/',method='GET',host='127.0.0.1:8944'):
        cls=serve.handler_for(self.site,8944);h=object.__new__(cls)
        h.path=path;h.headers={'Host':host};h.command=method;h.request_version='HTTP/1.1'
        h.requestline=f'{method} {path} HTTP/1.1';h.wfile=io.BytesIO();h.close_connection=True
        return h

    def test_generated_index_and_bundle_served_with_security_headers(self):
        for path in ['/','/index.html','/bundle.json','/index.html?view=synthetic']:
            with self.subTest(path=path):
                h=self.handler(path);h.do_GET();raw=h.wfile.getvalue()
                self.assertTrue(raw.startswith(b'HTTP/1.0 200'))
                self.assertIn(b'Cache-Control: no-store',raw)
                self.assertIn(b'X-Content-Type-Options: nosniff',raw)

    def test_head_has_no_payload(self):
        h=self.handler('/index.html','HEAD');h.do_HEAD()
        self.assertEqual(h.wfile.getvalue().split(b'\r\n\r\n',1)[1],b'')

    def test_unknown_files_traversal_encoded_paths_and_directory_listing_refused(self):
        for path in ['/private.txt','/nested/','/../private.txt','/%2e%2e/private.txt','/.git/config','/config.json']:
            with self.subTest(path=path):
                h=self.handler(path);h.do_GET();raw=h.wfile.getvalue()
                self.assertTrue(raw.startswith(b'HTTP/1.0 404'))
                self.assertNotIn(b'SYNTHETIC EXCLUDED',raw)

    def test_wrong_host_is_refused(self):
        h=self.handler('/',host='example.invalid:8944');h.do_GET()
        self.assertTrue(h.wfile.getvalue().startswith(b'HTTP/1.0 404'))

    def test_path_resolution_escape_is_refused(self):
        h=self.handler('/index.html')
        original=Path.resolve
        def resolve(path,*a,**kw):
            return self.temp/'outside.html' if path==self.site/'index.html' else original(path,*a,**kw)
        with patch.object(Path,'resolve',resolve):self.assertIsNone(h.admitted_path())

    def test_non_generated_root_refused_before_bind(self):
        with patch.object(serve,'HTTPServer') as server:
            with self.assertRaises(ValueError):serve.run_preview(ROOT,1)
            server.assert_not_called()

    def test_non_synthetic_bundle_refused(self):
        root=self.temp/'non-synthetic';root.mkdir();(root/'index.html').write_text('test',encoding='utf-8')
        value=json.loads((self.site/'bundle.json').read_text());value['candidates']['fiction-a']['synthetic_only']=False
        value.pop('bundle_sha256');value['bundle_sha256']=review.digest(value)
        (root/'bundle.json').write_text(json.dumps(value),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'real_material_read_only'):serve.admit_preview(root)

    def test_configuration_requires_loopback_and_integer_port(self):
        for host,port in [('0.0.0.0',8944),('127.0.0.1',True),('127.0.0.1',-1),('127.0.0.1',65536)]:
            with self.subTest(host=host,port=port):
                p=self.temp/'settings.json';p.write_text(json.dumps({'host':host,'port':port}),encoding='utf-8')
                with self.assertRaises(ValueError):serve.load_settings(p)

    def test_invalid_timeout_cannot_bind(self):
        for seconds in [0,-1,1801,True,float('nan'),float('inf')]:
            with self.subTest(seconds=seconds),patch.object(serve,'HTTPServer') as server:
                with self.assertRaises(ValueError):serve.run_preview(self.site,seconds)
                server.assert_not_called()

    def test_owned_server_closed_after_timeout_without_real_socket(self):
        server=Mock();server.server_address=('127.0.0.1',8944)
        with patch.object(serve,'HTTPServer',return_value=server),patch.object(serve.time,'monotonic',side_effect=[0,.1,1.1]),patch('sys.stdout',new=io.StringIO()):
            serve.run_preview(self.site,1)
        server.handle_request.assert_called_once();server.server_close.assert_called_once()

    def test_owned_server_closed_after_handler_error(self):
        server=Mock();server.server_address=('127.0.0.1',8944);server.handle_request.side_effect=RuntimeError('synthetic failure')
        with patch.object(serve,'HTTPServer',return_value=server),patch.object(serve.time,'monotonic',side_effect=[0,.1]),patch('sys.stdout',new=io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'synthetic failure'):serve.run_preview(self.site,1)
        server.server_close.assert_called_once()


if __name__=='__main__':unittest.main()
