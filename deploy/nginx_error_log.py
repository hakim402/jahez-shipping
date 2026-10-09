"""Nginx syslog privacy sink: retain only severity/time/event, never raw datagrams."""
import argparse
import json
import os
import re
import socket
from datetime import datetime,timezone
from pathlib import Path

def safe_record(payload):
    match=re.match(rb'^<(\d{1,3})>',payload)
    severity=int(match[1])%8 if match else 4
    return {'time':datetime.now(timezone.utc).isoformat(),'event':'shipping.nginx.error','severity':severity}

def append(path,record):
    if path.exists() and path.stat().st_size>=10*1024*1024:
        for i in (2,1):
            prior=Path(str(path)+'.'+str(i-1)) if i>1 else path
            if prior.exists():prior.replace(Path(str(path)+'.'+str(i)))
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    with os.fdopen(fd,'w') as handle:handle.write(json.dumps(record)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--systemd',action='store_true');parser.add_argument('--socket');parser.add_argument('--output',required=True);args=parser.parse_args()
    if args.systemd:
        if os.environ.get('LISTEN_FDS')!='1' or os.environ.get('LISTEN_PID')!=str(os.getpid()):raise SystemExit('One systemd datagram socket is required.')
        sock=socket.socket(fileno=3)
    else:
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);sock.bind(args.socket);os.chmod(args.socket,0o622)
    while True:
        payload=sock.recv(32768)
        try:append(Path(args.output),safe_record(payload))
        except OSError:
            import sys
            print('shipping.nginx.log_write_failed',file=sys.stderr)  # Static diagnostic, never the datagram.
