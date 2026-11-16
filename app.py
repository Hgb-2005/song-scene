"""Start the local Song & Scene workspace. No pip dependencies."""
from pathlib import Path
import argparse
import threading
import webbrowser

from server.http import Workspace, make_server

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8866)
    parser.add_argument('--data-dir',type=Path,default=ROOT/'data')
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    if not 1024<=args.port<=65535: parser.error('Port must be between 1024 and 65535')
    workspace=Workspace(ROOT,args.data_dir)
    try:
        server=make_server(workspace,args.port)
    except OSError:
        workspace.close()
        raise SystemExit(f'Port {args.port} is occupied. Close the older workspace or use --port {args.port+1}.')
    url=f'http://127.0.0.1:{server.server_port}/index.html'
    print(f'Song & Scene V8: {url}',flush=True)
    print(f'Data folder: {workspace.store.directory}',flush=True)
    print('Keep this window open. Ctrl+C stops the service.',flush=True)
    if args.open: threading.Timer(.5,lambda:webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close(); workspace.close()


if __name__=='__main__': main()
