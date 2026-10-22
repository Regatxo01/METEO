"""Servidor local de METEO. No expone la API key a Internet."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
import os
import threading
import webbrowser
import alertas_cp

BASE = Path(__file__).resolve().parent
os.chdir(BASE)
lock = threading.Lock()
class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, max-age=0')
        super().end_headers()
    def do_POST(self):
        if self.path != '/api/actualizar':
            self.send_error(404)
            return
        if not lock.acquire(blocking=False):
            self.responder(409, {'error': 'Ya hay una actualización en curso'})
            return
        try:
            # Generar la página antes de sustituir los archivos publicados.
            alertas_cp.abrir_archivo = lambda _: None
            alertas_cp.main()
            import shutil
            shutil.copyfile(BASE/'alertas_edificios.html', BASE/'index.html')
            self.responder(200, {'ok': True})
        except Exception as exc:
            self.responder(500, {'error': str(exc)})
        finally:
            lock.release()
    def responder(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 8765), Handler)
    print('METEO disponible en http://127.0.0.1:8765/')
    webbrowser.open('http://127.0.0.1:8765/')
    server.serve_forever()
