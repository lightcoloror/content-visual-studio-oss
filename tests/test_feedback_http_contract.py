"""Real request-handler code with simulated socket/process objects only."""
import io,json,sys,types,unittest
from unittest.mock import Mock,patch
import feedback_fixture
f=feedback_fixture.f


class FeedbackHttpContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=f.W/'feedback-http';cls.config=feedback_fixture.create(cls.root/'preview')

    def payload(self):
        row=self.config['candidates'][0]
        return {'key':row['key'],'version':row['binding']['candidate']['sha256'],'action':'edit',
            'reason':'Synthetic request-handler test','minutes':None,'baseline_minutes':None}

    def exercise(self,callback,threads=1):
        process=types.SimpleNamespace(pid=12345,create_time=lambda:1.0,num_threads=lambda:threads,
            memory_info=lambda:types.SimpleNamespace(rss=1024),children=lambda recursive:[])
        server=Mock();captured={}
        def constructor(address,handler):
            captured['handler']=handler
            return server
        server.handle_request.side_effect=lambda:callback(captured['handler'])
        with patch.dict(sys.modules,{'psutil':types.SimpleNamespace(Process=lambda:process)}),\
                patch.object(f,'HTTPServer',side_effect=constructor) as factory,\
                patch.object(f.time,'monotonic',side_effect=[0,.1,.2,1.1,1.2]),\
                patch.object(f.secrets,'token_urlsafe',return_value='synthetic-test-token'),\
                patch('sys.stdout',new=io.StringIO()):
            f.run_server(self.root/'preview',1)
        return server

    def request(self,handler,path,method='POST',headers=None,payload=None):
        raw=json.dumps(payload or self.payload()).encode()
        h=object.__new__(handler);h.path=path;h.command=method
        h.headers={'Host':'127.0.0.1:8944','Origin':'http://127.0.0.1:8944',
            'X-Feedback-Token':'synthetic-test-token','Content-Type':'application/json','Content-Length':str(len(raw))}
        h.headers.update(headers or {})
        h.rfile=io.BytesIO(raw);h.wfile=io.BytesIO();h.request_version='HTTP/1.1'
        h.requestline=f'{method} {path} HTTP/1.1';h.close_connection=True
        getattr(h,'do_'+method)()
        output=h.wfile.getvalue();status=int(output.split(b' ',2)[1]);body=output.split(b'\r\n\r\n',1)[1]
        return status,body

    def test_host_origin_and_token_must_all_match_before_submit(self):
        def callback(handler):
            with patch.object(f,'submit') as submit:
                for headers in [{'Host':'example.invalid:8944'},{'Origin':'http://example.invalid'},
                                {'X-Feedback-Token':'wrong'},{'X-Feedback-Token':''}]:
                    status,_=self.request(handler,'/feedback/submit',headers=headers)
                    self.assertEqual(status,403)
                submit.assert_not_called()
        self.exercise(callback).server_close.assert_called_once()

    def test_bad_content_type_or_body_size_is_rejected(self):
        def callback(handler):
            with patch.object(f,'submit') as submit:
                for headers in [{'Content-Type':'text/plain'},{'Content-Length':'0'},{'Content-Length':'16385'}]:
                    status,_=self.request(handler,'/feedback/submit',headers=headers)
                    self.assertEqual(status,400)
                submit.assert_not_called()
        self.exercise(callback)

    def test_context_returns_exact_candidate_version_and_session_token(self):
        def callback(handler):
            status,raw=self.request(handler,'/feedback/context','GET')
            value=json.loads(raw);self.assertEqual(status,200)
            self.assertEqual(value['token'],'synthetic-test-token')
            self.assertEqual(value['candidates'][0]['version'],self.payload()['version'])
        self.exercise(callback)

    def test_authorized_handler_uses_real_candidate_only_feedback_owner(self):
        def callback(handler):
            status,raw=self.request(handler,'/feedback/submit')
            value=json.loads(raw);self.assertEqual(status,200)
            self.assertEqual(value['decision'],'adopted_with_edits')
            self.assertIsNone(value['time_saved_minutes']);self.assertIsNone(value['publication'])
            self.assertEqual(value['scheduled_tasks'],[]);self.assertEqual(value['status'],'candidate_only')
        self.exercise(callback)

    def test_simulated_resource_limit_blocks_before_socket_factory(self):
        process=types.SimpleNamespace(pid=12345,create_time=lambda:1.0,num_threads=lambda:17,
            memory_info=lambda:types.SimpleNamespace(rss=1024))
        with patch.dict(sys.modules,{'psutil':types.SimpleNamespace(Process=lambda:process)}),patch.object(f,'HTTPServer') as factory:
            with self.assertRaisesRegex(ValueError,'resource_limit_before_listen'):
                f.run_server(self.root/'preview',1)
            factory.assert_not_called()


if __name__=='__main__':unittest.main()
