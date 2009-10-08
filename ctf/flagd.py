#! /usr/bin/env python3

import asyncore
import asynchat
import socket
import functools
import time
import hmac
import optparse
import os
import traceback
from . import teams
from . import points
from . import pointscli
from . import config

key = b'My First Shared Secret (tm)'
def hexdigest(data):
    return hmac.new(key, data).hexdigest()

flags_dir = config.get('global', 'flags_dir')

class Flagger(asynchat.async_chat):
    """Use to connect to flagd and submit the current flag holder."""

    def __init__(self, addr, auth):
        asynchat.async_chat.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect((addr, 6668))
        self.push(auth + b'\n')
        self.flag = None

    def handle_read(self):
        msg = self.recv(4096)
        raise ValueError("Flagger died: %r" % msg)

    def handle_error(self):
        # If we lose the connection to flagd, nobody can score any
        # points.  Terminate everything.
        asyncore.close_all()
        asynchat.async_chat.handle_error(self)

    def set_flag(self, team):
        if team:
            eteam = team.encode('utf-8')
        else:
            eteam = b''
        self.push(eteam + b'\n')
        self.flag = team
class Submitter(asyncore.dispatcher):
    def __init__(self, host='127.0.0.1', port=6667):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.connect((host, port))
        self.pending = []
        self.unacked = {}
        self.flags = {}
        self.lastupdate = 0
        self.lastretrans = 0
        self.id = 0

    def submit(self, now, cat, team, score):
        q = points.encode_request(self.id, now, cat, team, score)
        self.id += 1
        self.pending.append(q)
        self.unacked[id] = q

    def writable(self):
        now = int(time.time())
        if now >= self.lastupdate + 60:
            for cat, team in self.flags.items():
                self.submit(now, cat, team, 1)
            self.lastupdate = now
        if now > self.lastretrans:
            for id, q in self.unacked.items():
                self.pending.append(q)
            self.lastretrans = now
        ret = bool(self.pending)
        return ret

    def handle_write(self):
        dgram = self.pending.pop(0)
        self.socket.send(dgram)

    def handle_read(self):
        dgram, peer = self.socket.recvfrom(4096)
        try:
            id, txt = points.decode_response(dgram)
        except ValueError:
            # Ignore invalid packets
            return
        try:
            del self.unacked[id]
        except KeyError:
            pass
        if txt != 'OK':
            raise ValueError(txt)

    def set_flag(self, cat, team):
        if not cat:
            return
        now = int(time.time())

        team = team or teams.house

        if self.flags.get(cat) != team:
            self.flags[cat] = team
            self.submit(now, cat, team, 1)


class Listener(asyncore.dispatcher):
    def __init__(self, connection_factory, host='', port=6668):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host, port))
        self.listen(4)
        self.connection_factory = connection_factory

    def handle_accept(self):
        conn, addr = self.accept()
        self.connection_factory(conn)


class FlagServer(asynchat.async_chat):
    def __init__(self, submitter, sock):
        asynchat.async_chat.__init__(self, sock=sock)
        self.set_terminator(b'\n')
        self.submitter = submitter
        self.flag = None
        self.inbuf = []
        self.cat = None

    def err(self, txt):
        e = ('ERROR: Closing Link: %s\n' % txt)
        self.push(e.encode('utf-8'))
        self.close()

    def collect_incoming_data(self, data):
        if len(self.inbuf) > 10:
            return self.err('max sendq exceeded')
        self.inbuf.append(data)

    def set_flag(self, team):
        if not self.cat:
            return
        self.flag = team
        self.submitter.set_flag(self.cat, team)
        f = open(os.path.join(flags_dir, self.cat), 'w')
        if team:
            f.write(team)

    def found_terminator(self):
        data = b''.join(self.inbuf)
        self.inbuf = []
        if not self.cat:
            try:
                cat, passwd = data.split(b':::')
                passwd = passwd.decode('utf-8')
                if passwd != hexdigest(cat):
                    return self.err('Invalid password')
                self.cat = cat.decode('utf-8')
            except ValueError:
                return self.err('Invalid command')
            self.set_flag(None)
        else:
            team = data.strip().decode('utf-8')
            self.set_flag(team)

    def handle_close(self):
        self.set_flag(None)
        self.close()


def start():
    submitter = Submitter()
    server = Listener(functools.partial(FlagServer, submitter))
    return (submitter, server)

def main():
    p = optparse.OptionParser()
    p.add_option('-p', '--genpass', dest='cat', default=None,
                 help='Generate a password for the given category')
    opts, args = p.parse_args()
    if opts.cat:
        print('%s:::%s' % (opts.cat, hexdigest(opts.cat.encode('utf-8'))))
        return

    start()
    asyncore.loop()

if __name__ == '__main__':
    main()
