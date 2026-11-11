"""Builder-side client for the oracle. Standard library only, so it can be copied into a builder workspace."""
import json
import socket


class OracleClient:
    def __init__(self, sock_path):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.connect(str(sock_path))
        self.f = self.s.makefile('rw', encoding='utf-8', newline='\n')

    def call(self, op, **fields):
        self.f.write(json.dumps({'op': op, **fields}) + '\n')
        self.f.flush()
        reply = json.loads(self.f.readline())
        if not reply.get('ok'):
            raise RuntimeError(reply.get('error', 'oracle error'))
        return reply

    def close(self):
        self.f.close()
        self.s.close()
