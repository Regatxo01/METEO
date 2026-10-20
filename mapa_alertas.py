"""
Mapa de alertas AEMET (naranja/rojo) por ubicación de sede.
Requiere monitor_aemet.py en la misma carpeta y la API key
(aemet_key.txt junto al programa, o variable AEMET_API_KEY).
Genera mapa_alertas.html y lo abre en el navegador.
"""
import json
import os
import sys
import webbrowser
from datetime import datetime

try:
    from monitor_aemet import EDIFICIOS, obtener_avisos, fmt
    from leaflet_embebido import LEAFLET_CSS, LEAFLET_JS
except Exception:
    import traceback
    print("ERROR al cargar el programa. Comprueba que en ESTA carpeta estan: "
          "monitor_aemet.py, mapa_alertas.py, leaflet_embebido.py y alertas_cp.py\n")
    traceback.print_exc()
    input("\nPulsa Enter para salir...")
    raise SystemExit(1)

# Coordenadas aproximadas (lat, lon). Ajústalas si quieres más precisión.
COORDS = {
    "V01": (39.4699, -0.3763), "V02": (39.4747, -0.3584), "V03": (39.4640, -0.3900),
    "V04": (39.4590, -0.3290), "V05": (39.4540, -0.3240), "V06": (39.4430, -0.3250),
    "V07": (39.4344, -0.4375), "V08": (39.4600, -0.3500), "V09": (39.1514, -0.4351),
    "V10": (39.4019, -0.4017), "V11": (38.9680, -0.1850), "V12": (39.6290, -0.5965),
    "V13": (39.4900, -0.4640), "V14": (39.4893, -0.4816), "V15": (39.5450, -0.3960),
    "V16": (39.4880, -1.1000), "V17": (39.6800, -0.2780), "V18": (39.6330, -0.2120),
    "V19": (39.2020, -0.3100), "V20": (39.4370, -0.4650), "V21": (38.9900, -0.5200),
    "C01": (39.9864, -0.0513), "C02": (39.9690, -0.0120), "C03": (39.9700, -0.0100),
    "C04": (39.9378, -0.1014), "C05": (40.4700, 0.4750),
    "A01": (38.3452, -0.4810), "A02": (38.3480, -0.4850), "A03": (38.3370, -0.4800),
    "A04": (38.3452, -0.4810), "A05": (38.3350, -0.4820), "A06": (38.2822, -0.5582),
    "A07": (38.3600, -0.4900), "A08": (38.7054, -0.4743), "A09": (38.5411, -0.1225),
    "A10": (38.8408, 0.1057), "A11": (38.2699, -0.6983), "A12": (38.4780, -0.7910),
    "A13": (38.0848, -0.9440), "A14": (38.6370, -0.8650),
}

ORDEN = {"": 0, "NARANJA": 1, "ROJO": 2}

PLANTILLA = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>Alertas AEMET - Sedes</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>__LEAFLET_CSS__</style>
<script>__LEAFLET_JS__</script>
<style>
 html,body{height:100%;margin:0;font-family:Segoe UI,Arial,sans-serif}
 #top{background:#1f2d3d;color:#fff;padding:8px 14px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}
 #top h1{font-size:16px;margin:0}
 .chip{padding:2px 9px;border-radius:10px;font-size:13px;color:#fff}
 #wrap{display:flex;height:calc(100% - 44px)}
 #side{width:320px;overflow:auto;border-right:1px solid #ccc;background:#fafafa}
 #map{flex:1;background:#e9edf0}
 .item{padding:8px 12px;border-bottom:1px solid #e3e3e3;cursor:pointer;font-size:13px}
 .item:hover{background:#eef3f8}
 .lvl{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
 .etq{font-size:11px;font-weight:600;padding:1px 5px;background:rgba(255,255,255,.88);border:1.5px solid #555;box-shadow:none;white-space:nowrap;color:#222}
 .etq.n-ROJO{border-color:#d32f2f;color:#b71c1c}
 .etq.n-NARANJA{border-color:#f57c00;color:#a64b00}
 .etq.n-OK{border-color:#2e7d32}
 .sin-etq .etq{display:none}
 .vacio{padding:14px;color:#2e7d32;font-size:14px}
 @media(max-width:700px){#side{display:none}}
</style></head><body>
<div id="top"><h1>Alertas AEMET - Sedes Comunitat Valenciana</h1>
 <span id="fecha"></span>
 <span class="chip" style="background:#d32f2f" id="nr"></span>
 <span class="chip" style="background:#f57c00" id="nn"></span>
 <span class="chip" style="background:#2e7d32" id="nv"></span>
 <label style="font-size:13px"><input type="checkbox" id="etq" checked> Mostrar nombres</label></div>
<div id="wrap"><div id="side"></div><div id="map"></div></div>
<script>
const D = __DATA__;
const COL = {ROJO:'#d32f2f', NARANJA:'#f57c00', '':'#2e7d32'};
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
document.getElementById('fecha').textContent = D.fecha;
document.getElementById('nr').textContent = D.rojas + ' sedes en rojo';
document.getElementById('nn').textContent = D.naranjas + ' sedes en naranja';
document.getElementById('nv').textContent = D.verdes + ' sin alerta';

const map = L.map('map');
const capa = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {maxZoom:18, attribution:'Tiles &copy; Esri'}).addTo(map);
let avisado = false;
capa.on('tileerror', () => { if (avisado) return; avisado = true;
  const b = document.createElement('div');
  b.style.cssText = 'position:absolute;z-index:1000;left:60px;top:10px;background:#fff3cd;border:1px solid #e0c36a;padding:6px 10px;font-size:13px;border-radius:4px';
  b.textContent = 'No se pueden cargar los mapas de fondo (red bloqueada o sin conexion). Se muestran los puntos sin fondo.';
  document.getElementById('map').appendChild(b); });
const bounds = [];
const side = document.getElementById('side');
const marcadores = [];

D.lugares.forEach((l, i) => {
  const color = COL[l.nivel];
  let html = '<b>' + esc(l.poblacion) + '</b><hr style="margin:4px 0">';
  html += l.sedes.map(s => '&bull; ' + esc(s)).join('<br>');
  if (l.alertas.length) {
    html += '<hr style="margin:4px 0">' + l.alertas.map(a =>
      '<span style="color:' + COL[a.nivel] + '"><b>' + a.nivel + '</b></span> ' +
      esc(a.fenomeno) + '<br><small>' + esc(a.inicio) + ' &rarr; ' + esc(a.fin) + '</small>').join('<br>');
  } else { html += '<hr style="margin:4px 0"><span style="color:#2e7d32">Sin alertas naranja/rojas</span>'; }
  const m = L.circleMarker([l.lat, l.lon], {
    radius: l.nivel ? 13 : 8, color: '#222', weight: 1.5, fillColor: color, fillOpacity: .85
  }).addTo(map).bindPopup(html);
  const _n = l.sedes;
  const _txt = _n.length <= 4 ? _n.map(esc).join('<br>') : esc(l.poblacion) + ' (' + _n.length + ' sedes)';
  m.bindTooltip(_txt, {permanent: true, direction: 'right', offset: [10, 0], className: 'etq n-' + (l.nivel || 'OK')});
  marcadores.push(m);
  bounds.push([l.lat, l.lon]);

  if (l.alertas.length) {
    const d = document.createElement('div');
    d.className = 'item';
    d.innerHTML = '<span class="lvl" style="background:' + color + '"></span><b>' + esc(l.poblacion) +
      '</b> (' + l.sedes.length + ' sede' + (l.sedes.length > 1 ? 's' : '') + ')<br><small>' +
      l.alertas.map(a => a.nivel + ': ' + esc(a.fenomeno)).join('<br>') + '</small>';
    d.onclick = () => { map.setView([l.lat, l.lon], 12); m.openPopup(); };
    side.appendChild(d);
  }
});
if (!side.children.length) side.innerHTML = '<div class="vacio">&#10003; Ninguna sede con alerta naranja o roja.</div>';
etq.onchange = () => document.body.classList.toggle('sin-etq', !etq.checked);
map.fitBounds(bounds, {padding: [30, 30]});
</script></body></html>
"""


def construir_datos(avisos):
    lugares = {}
    for e in EDIFICIOS:
        id_, nombre, poblacion, provincia, zona = e
        lat, lon = COORDS[id_]
        clave = (round(lat, 3), round(lon, 3))
        lug = lugares.setdefault(clave, {
            "lat": lat, "lon": lon, "poblacion": poblacion,
            "sedes": [], "alertas": [], "nivel": "", "_vistos": set()})
        lug["sedes"].append(nombre)
        for a in avisos:
            if a["zona"] == zona:
                k = (a["nivel"], a["fenomeno"], a["inicio"], a["fin"])
                if k not in lug["_vistos"]:
                    lug["_vistos"].add(k)
                    lug["alertas"].append({
                        "nivel": a["nivel"], "fenomeno": a["fenomeno"],
                        "inicio": fmt(a["inicio"]), "fin": fmt(a["fin"])})
                if ORDEN[a["nivel"]] > ORDEN[lug["nivel"]]:
                    lug["nivel"] = a["nivel"]
    lista = []
    for l in lugares.values():
        l.pop("_vistos")
        lista.append(l)
    rojas = sum(len(l["sedes"]) for l in lista if l["nivel"] == "ROJO")
    naranjas = sum(len(l["sedes"]) for l in lista if l["nivel"] == "NARANJA")
    total = sum(len(l["sedes"]) for l in lista)
    return {
        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "rojas": rojas, "naranjas": naranjas, "verdes": total - rojas - naranjas,
        "lugares": lista,
    }


def carpeta_base():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


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
    print("Consultando avisos de AEMET...")
    avisos = obtener_avisos()
    datos = construir_datos(avisos)
    html = (PLANTILLA.replace("__DATA__", json.dumps(datos, ensure_ascii=False))
            .replace("__LEAFLET_CSS__", LEAFLET_CSS)
            .replace("__LEAFLET_JS__", LEAFLET_JS))
    ruta = os.path.join(carpeta_base(), "mapa_alertas.html")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Mapa generado: {ruta}")
    abrir_archivo(ruta)


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
