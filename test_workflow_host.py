"""Isolated acceptance-test host. Never imported or bundled by the desktop app."""
import os,sys
import server

class TestHandler(server.Handler):
    def do_POST(self):
        if self.path=='/__test/crash' and self.headers.get('X-Test-Token')==os.environ['MANJU_TEST_TOKEN']:
            self.local_check()
            # Terminate only this host's own encoders, then exit without saving task state.
            # Holding the lock prevents a worker from turning the persisted running state into failed.
            with server.LOCK:
                for job in server.JOBS.values():
                    for process in list(job['processes']):
                        try:process.kill()
                        except OSError:pass
                os._exit(91)
        return super().do_POST()

if __name__=='__main__':
    server.ThreadingHTTPServer(('127.0.0.1',int(sys.argv[1])),TestHandler).serve_forever()
