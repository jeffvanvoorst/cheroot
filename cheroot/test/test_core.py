"""Basic tests for the Cheroot server: request handling."""

import time

from cheroot._compat import ntob, HTTPConnection, HTTPSConnection
from cheroot.test import helper


class CoreRequestHandlingTest(helper.CherootWebCase):

    def setup_server(cls):
        class Root(helper.Controller):

            def hello(self, req, resp):
                return "hello"

            def echo(self, req, resp):
                output = req.environ['wsgi.input'].read()
                return output.decode("ISO-8859-1")

            def echo_lines(self, req, resp):
                output = []
                while True:
                    line = req.environ['wsgi.input'].readline().decode("ISO-8859-1")
                    if not line:
                        break
                    output.append(line)
                return output

            def normal(self, req, resp):
                return "normal"
            
            def blank(self, req, resp):
                resp.status = ""
                return ""
            
            # According to RFC 2616, new status codes are OK as long as they
            # are between 100 and 599.
            
            # Here is an illegal code...
            def illegal(self, req, resp):
                resp.status = '781'
                return "oops"
            
            # ...and here is an unknown but legal code.
            def unknown(self, req, resp):
                resp.status = "431 My custom error"
                return "funky"
            
            # Non-numeric code
            def bad(self, req, resp):
                resp.status = "error"
                return "bad news"

            def header_list(self, req, resp):
                # helper.Controller.__call__ will transform this into
                # multiple headers with the same name, which is what
                # we're trying to test
                resp.headers['WWW-Authenticate'] = [
                    'Negotiate','Basic realm="foo"']
                return ""
            
            def commas(self, req, resp):
                resp.headers['WWW-Authenticate'] = 'Negotiate,Basic realm="foo"'
                return ""

            def start_response_error(self, req, resp):
                resp.headers[2] = 3
                return "salud!"

        cls.httpserver.wsgi_app = Root()
    setup_server = classmethod(setup_server)

    def test_status_normal(self):
        self.getPage("/normal")
        self.assertBody('normal')
        self.assertStatus(200)

    def test_status_blank(self):
        self.getPage("/blank")
        self.assertStatus(200)

    def test_status_illegal(self):
        self.getPage("/illegal")
        self.assertStatus(500)
        self.assertInBody(
            "Illegal response status from server (781 is out of range).")

    def test_status_unknown(self):
        self.getPage("/unknown")
        self.assertBody('funky')
        self.assertStatus(431)

    def test_status_syntax_error(self):
        self.getPage("/bad")
        self.assertStatus(500)
        self.assertStatus(500)
        self.assertInBody(
            "Illegal response status from server (%s is non-numeric)." %
            (repr(ntob('error'))))

    def test_multiple_headers(self):
        self.getPage('/header_list')
        self.assertEqual([(k, v) for k, v in self.headers if k == 'WWW-Authenticate'],
                         [('WWW-Authenticate', 'Negotiate'),
                          ('WWW-Authenticate', 'Basic realm="foo"'),
                          ])
        self.getPage('/commas')
        self.assertHeader('WWW-Authenticate', 'Negotiate,Basic realm="foo"')

    def test_start_response_error(self):
        self.getPage("/start_response_error")
        self.assertStatus(500)
        self.assertInBody("TypeError: WSGI response header key 2 is not of type str.")

    def test_request_payload(self):
        if self.scheme == "https":
            c = HTTPSConnection('%s:%s' % (self.interface(), self.PORT))
        else:
            c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c.putrequest("POST", "/echo")
        body = ntob("I am a request body")
        c.putheader("Content-Length", len(body))
        c.endheaders()
        c.send(body)
        response = c.getresponse()
        self.body = response.read()
        c.close()
        self.status = str(response.status)
        self.assertStatus(200)
        self.assertBody(body)

    def test_chunked_request_payload(self):
        if self.scheme == "https":
            c = HTTPSConnection('%s:%s' % (self.interface(), self.PORT))
        else:
            c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c.putrequest("POST", "/echo")
        c.putheader("Transfer-Encoding", "chunked")
        c.endheaders()
        c.send(ntob("13\r\nI am a request body\r\n0\r\n\r\n"))
        response = c.getresponse()
        self.body = response.read()
        c.close()
        self.status = str(response.status)
        self.assertStatus(200)
        self.assertBody("I am a request body")

    def test_chunked_request_payload_readline(self):
        if self.scheme == "https":
            c = HTTPSConnection('%s:%s' % (self.interface(), self.PORT))
        else:
            c = HTTPConnection('%s:%s' % (self.interface(), self.PORT))
        c.putrequest("POST", "/echo_lines")
        c.putheader("Transfer-Encoding", "chunked")
        c.endheaders()
        c.send(ntob("13\r\nI am a\nrequest body\r\n0\r\n\r\n"))
        response = c.getresponse()
        self.body = response.read()
        c.close()
        self.status = str(response.status)
        self.assertStatus(200)
        self.assertBody("I am a\nrequest body")


class ServerInterruptTest(helper.CherootWebCase):

    def setup_server(cls):
        class Root(helper.Controller):

            def hello(self, req, resp):
                return "hello"

            def kbint(self, req, resp):
                cls.httpserver.interrupt = KeyboardInterrupt()
                return "hello"

        cls.httpserver.wsgi_app = Root()
    setup_server = classmethod(setup_server)

    def test_kbint(self):
        self.getPage("/kbint")
        # Note that our request thread will complete normally even though
        # the server is shutting down, which is *usually* a nice thing
        # but not always.
        self.assertStatus(200)
        self.assertBody("hello")
        # Give the server accept() thread time to shut down
        time.sleep(1)
        self.assertInLog("Keyboard Interrupt: shutting down")

