"""
Alertas AEMET (naranja/rojo) por edificio, con código postal, en mapa + listado.

Necesita en la misma carpeta: monitor_aemet.py y mapa_alertas.py
y la API key (aemet_key.txt junto al programa, o variable AEMET_API_KEY).

Edificios: se leen de edificios.csv (separador ;). Si no existe, se crea una
plantilla con las 40 sedes para que rellenes los códigos postales (columna cp).
Ubicación de cada edificio, por orden de prioridad:
  1) lat/lon escritas a mano en el CSV
  2) geocodificación del código postal (OpenStreetMap/Nominatim, se guarda en geocache.json)
  3) coordenadas aproximadas del municipio (las de mapa_alertas.py)
El cruce con AEMET se hace por polígono del aviso (si el aviso lo trae) y,
si no, por código de zona.
"""
import csv
import io
import json
import os
import sys
import tarfile
import time
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
try:
    import monitor_aemet as M
    from leaflet_embebido import LEAFLET_CSS, LEAFLET_JS
    from mapa_alertas import COORDS
except Exception:
    import traceback
    print("ERROR al cargar el programa. Comprueba que en ESTA carpeta estan: "
          "monitor_aemet.py, mapa_alertas.py, leaflet_embebido.py y alertas_cp.py\n")
    traceback.print_exc()
    input("\nPulsa Enter para salir...")
    raise SystemExit(1)

COLS = ["id", "nombre", "direccion", "cp", "poblacion", "provincia", "lat", "lon"]
ORDEN = {"": 0, "NARANJA": 1, "ROJO": 2}


def carpeta_base():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def ruta(nombre):
    return os.path.join(carpeta_base(), nombre)


# ---------------------------------------------------------------- edificios
def crear_plantilla():
    with open(ruta("edificios.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(COLS)
        for id_, nombre, poblacion, provincia, _zona in M.EDIFICIOS:
            w.writerow([id_, nombre, "", "", poblacion, provincia, "", ""])


def _num(s):
    try:
        return float(str(s).replace(",", ".").strip())
    except ValueError:
        return None


def leer_edificios():
    if not os.path.exists(ruta("edificios.csv")):
        crear_plantilla()
        print("Se ha creado edificios.csv con las 40 sedes (sin códigos postales).")
        print("Ábrelo con Excel, rellena la columna cp (y la dirección si quieres) y vuelve a ejecutar.\n")
    zonas = {e[0]: e[4] for e in M.EDIFICIOS}
    edificios = []
    with open(ruta("edificios.csv"), newline="", encoding="utf-8-sig") as f:
        for fila in csv.DictReader(f, delimiter=";"):
            id_ = (fila.get("id") or "").strip()
            if not id_:
                continue
            edificios.append({
                "id": id_,
                "nombre": (fila.get("nombre") or "").strip(),
                "direccion": (fila.get("direccion") or "").strip(),
                "cp": (fila.get("cp") or "").strip(),
                "poblacion": (fila.get("poblacion") or "").strip(),
                "provincia": (fila.get("provincia") or "").strip(),
                "lat": _num(fila.get("lat")),
                "lon": _num(fila.get("lon")),
                "zona": zonas.get(id_),
            })
    return edificios


# -------------------------------------------------------------- geocodificar
def _cargar_cache():
    try:
        with open(ruta("geocache.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _guardar_cache(cache):
    try:
        with open(ruta("geocache.json"), "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def geocodificar_cp(cp, cache):
    if cp in cache:
        return cache[cp]
    url = ("https://nominatim.openstreetmap.org/search?format=json&limit=1&country=es&postalcode="
           + urllib.parse.quote(cp))
    req = urllib.request.Request(url, headers={"User-Agent": "MonitorAlertasSedes/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            datos = json.loads(r.read().decode("utf-8"))
        cache[cp] = [float(datos[0]["lat"]), float(datos[0]["lon"])] if datos else None
    except Exception:
        return None  # no se cachea el fallo de red
    time.sleep(1.1)  # política de uso de Nominatim
    return cache[cp]


def asignar_ubicacion(edificios):
    cache = _cargar_cache()
    for e in edificios:
        if e["lat"] is not None and e["lon"] is not None:
            e["origen"] = "manual"
            continue
        pos = geocodificar_cp(e["cp"], cache) if e["cp"] else None
        if pos:
            e["lat"], e["lon"] = pos
            e["origen"] = "código postal"
        elif e["id"] in COORDS:
            e["lat"], e["lon"] = COORDS[e["id"]]
            e["origen"] = "aprox. municipio"
        else:
            e["origen"] = "sin ubicación"
    _guardar_cache(cache)


# ------------------------------------------------------------------- AEMET
def parsear_cap(xml_data):
    root = ET.fromstring(xml_data)
    ns = M.NS
    res = []
    for info in root.findall("cap:info", ns):
        lang = info.findtext("cap:language", default="", namespaces=ns)
        if lang and not lang.lower().startswith("es"):
            continue
        nivel = M.NIVELES.get(info.findtext("cap:severity", default="", namespaces=ns))
        if not nivel:
            continue
        for area in info.findall("cap:area", ns):
            zona = None
            for gc in area.findall("cap:geocode", ns):
                if gc.findtext("cap:valueName", namespaces=ns) == "EMMA_ID":
                    zona = gc.findtext("cap:value", namespaces=ns)
            poligonos = []
            for p in area.findall("cap:polygon", ns):
                try:
                    pts = [tuple(float(v) for v in par.split(",")) for par in p.text.split()]
                    if len(pts) >= 3:
                        poligonos.append(pts)
                except (ValueError, AttributeError):
                    pass
            res.append({
                "zona": zona,
                "zona_nombre": area.findtext("cap:areaDesc", default="", namespaces=ns),
                "poligonos": poligonos,
                "nivel": nivel,
                "fenomeno": info.findtext("cap:event", default="Meteorología adversa", namespaces=ns),
                "inicio": info.findtext("cap:onset", default=info.findtext("cap:effective", default="", namespaces=ns), namespaces=ns),
                "fin": info.findtext("cap:expires", default="", namespaces=ns),
            })
    return res


def obtener_avisos():
    if not M.API_KEY:
        raise SystemExit("Falta la API key: crea aemet_key.txt junto al programa con tu clave.")
    url = (f"https://opendata.aemet.es/opendata/api/avisos_cap/"
           f"ultimoelaborado/area/{M.AREA}?api_key={M.API_KEY}")
    meta = json.loads(M._get(url).decode("utf-8"))
    if meta.get("estado") != 200:
        raise SystemExit(f"Error AEMET: {meta.get('descripcion')}")
    contenido = M._get(meta["datos"])
    avisos = []
    with tarfile.open(fileobj=io.BytesIO(contenido)) as tar:
        for m in tar.getmembers():
            if m.isfile():
                avisos.extend(parsear_cap(tar.extractfile(m).read()))
    return avisos


def punto_en_poligono(lat, lon, poligono):
    """Ray casting. Los polígonos CAP vienen como lat,lon."""
    dentro = False
    n = len(poligono)
    j = n - 1
    for i in range(n):
        yi, xi = poligono[i]
        yj, xj = poligono[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def cruzar(edificios, avisos):
    hay_poligonos = any(a["poligonos"] for a in avisos)
    for e in edificios:
        alertas, vistos, nivel = [], set(), ""
        for a in avisos:
            coincide = False
            if a["poligonos"] and e["lat"] is not None:
                coincide = any(punto_en_poligono(e["lat"], e["lon"], p) for p in a["poligonos"])
            elif e["zona"] and a["zona"] == e["zona"]:
                coincide = True
            if coincide:
                k = (a["nivel"], a["fenomeno"], a["inicio"], a["fin"])
                if k not in vistos:
                    vistos.add(k)
                    alertas.append({"nivel": a["nivel"], "fenomeno": a["fenomeno"],
                                    "inicio": M.fmt(a["inicio"]), "fin": M.fmt(a["fin"])})
                if ORDEN[a["nivel"]] > ORDEN[nivel]:
                    nivel = a["nivel"]
        e["alertas"], e["nivel"] = alertas, nivel
        e["cruce"] = "polígono" if (hay_poligonos and e["lat"] is not None) else "código de zona"


# --------------------------------------------------------------------- HTML
PLANTILLA = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>Alertas AEMET - Edificios</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<style>__LEAFLET_CSS__</style>
<script>__LEAFLET_JS__</script>
<style>
 html,body{height:100%;margin:0;font-family:Segoe UI,Arial,sans-serif}
 #top{background:#1f2d3d;color:#fff;padding:8px 14px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
 #top h1{font-size:16px;margin:0}
 .chip{padding:2px 9px;border-radius:10px;font-size:13px;color:#fff}
 #wrap{display:flex;height:calc(100% - 44px)}
 #side{width:370px;display:flex;flex-direction:column;border-right:1px solid #ccc;background:#fafafa}
 #ctl{padding:8px;border-bottom:1px solid #ddd;font-size:13px}
 #ctl input[type=text]{width:95%;padding:5px;margin-bottom:5px}
 #lista{overflow:auto;flex:1}
 #map{flex:1;background:#e9edf0}
 .item{padding:7px 12px;border-bottom:1px solid #e6e6e6;cursor:pointer;font-size:13px}
 .item:hover{background:#eef3f8}
 .lvl{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
 .cp{background:#e8eef5;border-radius:4px;padding:0 5px;font-size:12px;margin-left:4px}
 small{color:#555}
 .etq{font-size:11px;font-weight:600;padding:1px 5px;background:rgba(255,255,255,.88);border:1.5px solid #555;box-shadow:none;white-space:nowrap;color:#222}
 .etq.n-ROJO{border-color:#d32f2f;color:#b71c1c}
 .etq.n-NARANJA{border-color:#f57c00;color:#a64b00}
 .etq.n-OK{border-color:#2e7d32}
 .sin-etq .etq{display:none}
 #acciones{display:flex;gap:6px;align-items:center;margin-left:auto}
 #acciones button{background:#fff;color:#182d40;border:0;border-radius:6px;padding:9px 12px;font-weight:600;cursor:pointer}
 #estado{font-size:11px;opacity:.85}
 @media(max-width:800px){
  #top{padding:8px;gap:7px}#top h1{width:100%}#acciones{margin-left:0}
  #wrap{height:calc(100dvh - 104px);min-height:300px;position:relative}
  #side{display:flex;position:absolute;z-index:1100;top:0;bottom:0;left:0;width:min(86vw,370px);box-shadow:2px 0 12px #0003;transform:translateX(-110%);transition:transform .2s}
  body.menu-abierto #side{transform:translateX(0)}
  #map{width:100%}
 }


 /* Cabecera adaptable para pantallas pequeñas */
 #top{box-sizing:border-box;display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:7px 12px;align-items:center;padding:8px 12px}
 #marca{grid-column:1;grid-row:1 / span 2;display:flex;align-items:center;background:#fff;border-radius:6px;padding:3px 5px}
 #marca img{display:block;width:106px;height:auto;max-height:51px;object-fit:contain}
 #top h1{grid-column:2;grid-row:1;font-size:15px;line-height:1.2;min-width:0}
 #fecha{grid-column:2;grid-row:2;font-size:11px}
 #acciones{grid-column:3;grid-row:1 / span 2;display:flex;align-items:center;gap:7px;margin-left:0}
 #acciones button{white-space:nowrap}
 #antiguedad,#reloj,#nr,#nn,#nv{font-size:12px}
 #wrap{height:calc(100dvh - var(--cabecera-alto, 90px));min-height:240px}
 @media(max-width:800px){
   #top{grid-template-columns:78px minmax(0,1fr);gap:6px 9px;padding:7px 9px}
   #marca{grid-column:1;grid-row:1 / span 2;padding:2px 3px}
   #marca img{width:72px;max-height:39px}
   #top h1{grid-column:2;grid-row:1;font-size:13px}
   #fecha{grid-column:2;grid-row:2;font-size:10px;overflow-wrap:anywhere}
   #antiguedad{grid-column:1 / -1;grid-row:3;justify-self:start}
   #reloj{grid-column:1 / -1;grid-row:4;font-size:11px}
   #nr{grid-column:1;grid-row:5;justify-self:stretch;text-align:center}
   #nn{grid-column:2;grid-row:5;justify-self:stretch;text-align:center}
   #nv{grid-column:1 / -1;grid-row:6;justify-self:start}
   #acciones{grid-column:1 / -1;grid-row:7;display:grid;grid-template-columns:1fr 1fr;gap:7px;width:100%}
   #acciones button{width:100%;min-height:38px;padding:8px 6px;font-size:13px}
   #estado{grid-column:1 / -1;min-height:0;overflow-wrap:anywhere}
   #side{width:min(86vw,370px)}
 }

/* Cabecera compacta y ordenada, con un único botón de menú */
#top{grid-template-columns:108px minmax(0,1fr) auto;gap:6px 12px;align-content:center}
#marca{grid-column:1;grid-row:1 / span 2}
#top h1{grid-column:2;grid-row:1;font-size:15px}
#fecha{grid-column:2;grid-row:2;font-size:11px}
#acciones{grid-column:3;grid-row:1 / span 2;display:flex;width:auto;gap:0}
#acciones button{min-height:38px}
#estado{display:none}
#antiguedad{grid-column:1 / 3;grid-row:3;justify-self:start}
#reloj{grid-column:3;grid-row:3;justify-self:end}
#nr{grid-column:1;grid-row:4;text-align:center}
#nn{grid-column:2;grid-row:4;text-align:center;justify-self:start}
#nv{grid-column:3;grid-row:4;text-align:center;justify-self:end}
@media(max-width:800px){
 #top{grid-template-columns:75px minmax(0,1fr) auto;gap:6px 8px;padding:7px 9px}
 #marca{grid-column:1;grid-row:1 / span 2}
 #marca img{width:69px;max-height:38px}
 #top h1{grid-column:2 / 4;grid-row:1;font-size:13px;line-height:1.2}
 #fecha{grid-column:2 / 4;grid-row:2;font-size:10px}
 #antiguedad{grid-column:1 / 3;grid-row:3;font-size:11px}
 #reloj{grid-column:3;grid-row:3;font-size:10px;text-align:right}
 #nr{grid-column:1;grid-row:4;font-size:11px}
 #nn{grid-column:2;grid-row:4;font-size:11px;justify-self:stretch}
 #nv{grid-column:3;grid-row:4;font-size:11px;justify-self:stretch}
 #acciones{grid-column:1 / -1;grid-row:5;display:flex;width:100%}
 #acciones button{width:100%;min-height:38px;font-size:13px}
}
@media(max-width:390px){#reloj{grid-column:1 / -1;grid-row:4;justify-self:start}#nr{grid-column:1;grid-row:5}#nn{grid-column:2;grid-row:5}#nv{grid-column:3;grid-row:5}#acciones{grid-row:6}}

/* Cabecera: reloj a la derecha de consulta y tres indicadores uniformes */
#antiguedad{grid-column:1 / 3;grid-row:3;justify-self:start}
#reloj{grid-column:3;grid-row:3;justify-self:end;white-space:nowrap}
#nr,#nn,#nv{grid-row:4;justify-self:stretch;text-align:center;display:flex;align-items:center;justify-content:center;min-width:0;box-sizing:border-box;border-radius:999px;padding:5px 8px;font-weight:600;white-space:nowrap}
@media(max-width:800px){
 #top{grid-template-columns:repeat(3,minmax(0,1fr));gap:6px 7px}
 #marca{grid-column:1;grid-row:1 / span 2}
 #top h1{grid-column:2 / 4;grid-row:1}
 #fecha{grid-column:2 / 4;grid-row:2}
 #antiguedad{grid-column:1 / 3;grid-row:3;font-size:11px}
 #reloj{grid-column:3;grid-row:3;font-size:10px;text-align:right;white-space:nowrap}
 #nr{grid-column:1;grid-row:4;font-size:11px}
 #nn{grid-column:2;grid-row:4;font-size:11px}
 #nv{grid-column:3;grid-row:4;font-size:11px}
 #acciones{grid-column:1 / -1;grid-row:5}
}
@media(max-width:390px){
 #reloj{grid-column:3;grid-row:3;justify-self:end;font-size:9px}
 #nr,#nn,#nv{grid-row:4;font-size:10px;padding:5px 3px}
 #acciones{grid-row:5}
}
</style></head><body>
<div id="top"><div id="marca"><img src="logo-agencia-tributaria.jpg" alt="Agencia Tributaria"></div><h1>Alertas AEMET - Edificios</h1><span id="fecha"></span><span id="antiguedad" class="chip" title="Tiempo desde la última consulta AEMET" style="background:#616161">Calculando antigüedad...</span><span id="reloj" title="Hora actual de España"></span>
 <span class="chip" style="background:#d32f2f" id="nr"></span>
 <span class="chip" style="background:#f57c00" id="nn"></span>
 <span class="chip" style="background:#2e7d32" id="nv"></span>
 <div id="acciones"><button type="button" id="abrirMenu">☰ Edificios</button><span id="estado"></span></div></div>
<div id="wrap"><div id="side">
 <div id="ctl"><input type="text" id="buscar" placeholder="Buscar por nombre, código postal, población...">
 <label><input type="checkbox" id="solo"> Solo edificios con alerta</label><br>
 <label><input type="checkbox" id="etq" checked> Mostrar nombres en el mapa</label></div>
 <div id="lista"></div></div><div id="map"></div></div>
<script>
const D = __DATA__;
// GitHub Pages sirve archivos estáticos: este botón comprueba una publicación nueva.
const ajustarAlturaCabecera = () => document.documentElement.style.setProperty('--cabecera-alto', document.getElementById('top').getBoundingClientRect().height + 'px');
ajustarAlturaCabecera();
window.addEventListener('resize', ajustarAlturaCabecera);
const menuBtn = document.getElementById('abrirMenu');
menuBtn.onclick = () => { document.body.classList.toggle('menu-abierto'); setTimeout(() => map.invalidateSize(),250); };
const estado = document.getElementById('estado');
const botonActualizar = null; // Actualización manual eliminada; comprobación automática activa
const urlPublicada = new URL('index.html', location.href);
function horaActual() {
 document.getElementById('reloj').textContent = 'España: ' + new Intl.DateTimeFormat('es-ES', {timeZone:'Europe/Madrid',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date());
}
horaActual(); setInterval(horaActual, 1000);
function actualizarAntiguedad() {
 const indicador = document.getElementById('antiguedad');
 const coincidencia = /^(\\d{2})\\/(\\d{2})\\/(\\d{4})\\s+(\\d{2}):(\\d{2})$/.exec(String(D.fecha || '').trim());
 if (!coincidencia) { indicador.textContent = 'Antigüedad: fecha no disponible'; indicador.style.background = '#616161'; return; }
 const [, dia, mes, anio, hora, minuto] = coincidencia;
 const fechaUTC = Date.UTC(+anio, +mes - 1, +dia, +hora, +minuto);
 const zona = new Intl.DateTimeFormat('en-US', {timeZone:'Europe/Madrid',timeZoneName:'shortOffset'}).formatToParts(new Date(fechaUTC));
 const textoZona = (zona.find(p => p.type === 'timeZoneName') || {}).value || 'GMT+1';
 const offset = /GMT([+-])(\\d{1,2})(?::(\\d{2}))?/.exec(textoZona);
 const minutosOffset = offset ? (offset[1] === '+' ? 1 : -1) * (+offset[2] * 60 + +(offset[3] || 0)) : 60;
 const momentoConsulta = fechaUTC - minutosOffset * 60000;
 const minutos = Math.max(0, Math.floor((Date.now() - momentoConsulta) / 60000));
 indicador.textContent = minutos < 1 ? 'Consultado hace menos de 1 min' : 'Consultado hace ' + minutos + ' min';
 const color = minutos < 20 ? '#2e7d32' : minutos <= 40 ? '#ef6c00' : '#c62828';
 indicador.style.background = color;
 indicador.title = minutos < 20 ? 'Actualizado' : minutos <= 40 ? 'Con retraso' : 'Sin actualizar hace más de 40 minutos';
}
actualizarAntiguedad();
setInterval(actualizarAntiguedad, 60000);

async function comprobarPublicacion(silencioso=false) {
 if (location.protocol === 'file:') { if(!silencioso) estado.textContent='Para actualizar desde GitHub, abre la web publicada.'; return; }
 if (botonActualizar) botonActualizar.disabled=true;
 if(!silencioso) estado.textContent='Comprobando última publicación de GitHub...';
 try {
  const u = new URL(urlPublicada.href); u.searchParams.set('_t', String(Date.now()));
  const r = await fetch(u.href, {cache:'no-store', headers:{'Cache-Control':'no-cache'}});
  if (!r.ok) throw new Error('HTTP '+r.status);
  const html = await r.text();
  const m = html.match(/const D\s*=\s*(\{[^\\r\\n]*\});/);
  if (!m) throw new Error('No se encuentra la fecha de la publicación');
  const remoto = JSON.parse(m[1]);
  if (remoto.fecha !== D.fecha) {
   estado.textContent='Hay datos nuevos. Cargando...';
   location.replace(u.href); return;
  }
  if(!silencioso) estado.textContent='Sin nueva publicación. Última consulta AEMET: '+D.fecha;
 } catch(e) { if(!silencioso) estado.textContent='No se pudo comprobar GitHub: '+e.message; }
 finally {if (botonActualizar) botonActualizar.disabled=false;}
}

// Revisa periódicamente si GitHub Actions ha publicado una consulta nueva.
setInterval(()=>comprobarPublicacion(true), 5*60*1000);

const COL = {ROJO:'#d32f2f', NARANJA:'#f57c00', '':'#2e7d32'};
const esc = s => String(s==null?'':s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
fecha.textContent = 'Última consulta AEMET: ' + D.fecha;
nr.textContent = D.rojas + ' en rojo'; nn.textContent = D.naranjas + ' en naranja'; nv.textContent = D.verdes + ' sin alerta';

const map = L.map('map');
const capa = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {maxZoom:18, attribution:'Tiles &copy; Esri'}).addTo(map);
let avisado = false;
capa.on('tileerror', () => { if (avisado) return; avisado = true;
  const b = document.createElement('div');
  b.style.cssText = 'position:absolute;z-index:1000;left:60px;top:10px;background:#fff3cd;border:1px solid #e0c36a;padding:6px 10px;font-size:13px;border-radius:4px';
  b.textContent = 'No se pueden cargar los mapas de fondo (red bloqueada o sin conexion). Se muestran los puntos sin fondo.';
  document.getElementById('map').appendChild(b); });

// agrupar edificios por ubicación
const grupos = {};
D.edificios.forEach(e => {
  if (e.lat == null) return;
  const k = e.lat.toFixed(3) + ',' + e.lon.toFixed(3);
  (grupos[k] = grupos[k] || []).push(e);
});
const marcador = {}, bounds = [];
Object.values(grupos).forEach(g => {
  let nivel = '';
  g.forEach(e => { if (e.nivel === 'ROJO' || (e.nivel === 'NARANJA' && nivel === '')) nivel = e.nivel; });
  let html = '';
  g.forEach(e => {
    html += '<b>' + esc(e.nombre) + '</b>' + (e.cp ? ' <span class="cp">CP ' + esc(e.cp) + '</span>' : '') +
      '<br><small>' + esc(e.direccion) + (e.direccion ? ', ' : '') + esc(e.poblacion) + '</small><br>';
    html += e.alertas.length ? e.alertas.map(a =>
      '<span style="color:' + COL[a.nivel] + '"><b>' + a.nivel + '</b></span> ' + esc(a.fenomeno) +
      ' <small>(' + esc(a.inicio) + ' &rarr; ' + esc(a.fin) + ')</small>').join('<br>')
      : '<span style="color:#2e7d32">Sin alertas naranja/rojas</span>';
    html += '<hr style="margin:6px 0">';
  });
  const m = L.circleMarker([g[0].lat, g[0].lon], {radius: nivel ? 13 : 8, color:'#222', weight:1.5,
    fillColor: COL[nivel], fillOpacity:.85}).addTo(map).bindPopup(html, {maxHeight: 300});
  const _n = g.map(e => e.nombre);
  const _txt = _n.length <= 4 ? _n.map(esc).join('<br>') : esc(g[0].poblacion) + ' (' + _n.length + ' sedes)';
  m.bindTooltip(_txt, {permanent: true, direction: 'right', offset: [10, 0], className: 'etq n-' + (nivel || 'OK')});
  g.forEach(e => marcador[e.id] = m);
  bounds.push([g[0].lat, g[0].lon]);
});
if (bounds.length) map.fitBounds(bounds, {padding:[30,30]}); else map.setView([39.4, -0.5], 8);

function pintar() {
  const q = buscar.value.toLowerCase();
  lista.innerHTML = '';
  D.edificios.filter(e => (!solo.checked || e.nivel) &&
     [e.nombre, e.cp, e.poblacion, e.direccion].join(' ').toLowerCase().includes(q))
  .forEach(e => {
    const d = document.createElement('div'); d.className = 'item';
    d.innerHTML = '<span class="lvl" style="background:' + COL[e.nivel] + '"></span><b>' + esc(e.nombre) + '</b>' +
      (e.cp ? '<span class="cp">' + esc(e.cp) + '</span>' : '<span class="cp" style="background:#fde">sin CP</span>') +
      '<br><small>' + esc(e.poblacion) + ' &middot; ubicación: ' + esc(e.origen) + '</small>' +
      (e.alertas.length ? '<br>' + e.alertas.map(a => '<small style="color:' + COL[a.nivel] + '"><b>' + a.nivel +
        '</b> ' + esc(a.fenomeno) + ' (' + esc(a.inicio) + ' &rarr; ' + esc(a.fin) + ')</small>').join('<br>') : '');
    d.onclick = () => { if (e.lat != null) { map.setView([e.lat, e.lon], 13); marcador[e.id].openPopup(); document.body.classList.remove('menu-abierto'); setTimeout(() => map.invalidateSize(),250); } };
    lista.appendChild(d);
  });
}
// Recuperar preferencias de visualización guardadas en este navegador.
const PREFS_METEO = 'meteo-preferencias-v1';
try {
  const preferencias = JSON.parse(localStorage.getItem(PREFS_METEO) || '{}');
  if (typeof preferencias.mostrarNombres === 'boolean') etq.checked = preferencias.mostrarNombres;
  if (typeof preferencias.soloAlertas === 'boolean') solo.checked = preferencias.soloAlertas;
} catch (e) { /* El navegador puede bloquear el almacenamiento; METEO sigue funcionando. */ }
function guardarPreferencias() {
  try {
    localStorage.setItem(PREFS_METEO, JSON.stringify({mostrarNombres: etq.checked, soloAlertas: solo.checked}));
  } catch (e) { /* Sin almacenamiento persistente disponible. */ }
}
document.body.classList.toggle('sin-etq', !etq.checked);
buscar.oninput = pintar;
solo.onchange = () => { pintar(); guardarPreferencias(); };
etq.onchange = () => { document.body.classList.toggle('sin-etq', !etq.checked); guardarPreferencias(); };
pintar();
</script></body></html>
"""


def abrir_archivo(path):
    """Abre el HTML con el navegador predeterminado (Windows: os.startfile)."""
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)
            return
    except OSError:
        pass
    import pathlib
    webbrowser.open(pathlib.Path(path).resolve().as_uri())

def main():
    edificios = leer_edificios()
    sin_cp = sum(1 for e in edificios if not e["cp"])
    print(f"{len(edificios)} edificios leídos ({sin_cp} sin código postal).")
    print("Calculando ubicaciones (la primera vez tarda ~1 s por código postal distinto)...")
    asignar_ubicacion(edificios)
    print("Consultando avisos de AEMET...")
    avisos = obtener_avisos()
    cruzar(edificios, avisos)

    edificios.sort(key=lambda e: (-ORDEN[e["nivel"]], e["nombre"]))
    rojas = sum(1 for e in edificios if e["nivel"] == "ROJO")
    naranjas = sum(1 for e in edificios if e["nivel"] == "NARANJA")
    datos = {
        "fecha": datetime.now(ZoneInfo("Europe/Madrid")).strftime("%d/%m/%Y %H:%M"),
        "rojas": rojas, "naranjas": naranjas,
        "verdes": len(edificios) - rojas - naranjas,
        "edificios": [{k: v for k, v in e.items() if k != "zona"} for e in edificios],
    }
    html = (PLANTILLA.replace("__DATA__", json.dumps(datos, ensure_ascii=False))
            .replace("__LEAFLET_CSS__", LEAFLET_CSS)
            .replace("__LEAFLET_JS__", LEAFLET_JS))
    salida = ruta("alertas_edificios.html")
    with open(salida, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Listo: {salida}")
    print(f"Edificios con alerta: {rojas} rojas, {naranjas} naranjas.")
    abrir_archivo(salida)
    return datos


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        print(e)
    except Exception:
        import traceback
        detalle = traceback.format_exc()
        print("\nERROR INESPERADO:\n" + detalle)
        try:
            with open(os.path.join(carpeta_base(), "error.log"), "w", encoding="utf-8") as f:
                f.write(detalle)
            print("(Detalle guardado en error.log)")
        except OSError:
            pass
    finally:
        input("\nPulsa Enter para salir...")
