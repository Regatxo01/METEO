"""
Monitor de avisos AEMET (naranja y rojo) para sedes de la Comunitat Valenciana.

Uso:
    export AEMET_API_KEY="tu_clave"      (Windows: set AEMET_API_KEY=tu_clave)
    python monitor_aemet.py
"""
import io
import json
import os
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

import sys


def _cargar_api_key():
    """Busca la clave en la variable AEMET_API_KEY o en aemet_key.txt
    (en la misma carpeta que el .exe / el script)."""
    clave = os.environ.get("AEMET_API_KEY")
    if clave:
        return clave.strip()
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                           else os.path.abspath(__file__))
    ruta = os.path.join(base, "aemet_key.txt")
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            return f.read().strip()
    return None


API_KEY = _cargar_api_key()
AREA = "77"  # Comunitat Valenciana
NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}

# Zonas Meteoalerta (VERIFICAR con el listado oficial de AEMET)
VAL_N, VAL_I, VAL_S = "774601", "774602", "774603"
CAS_N, CAS_I, CAS_S = "771201", "771202", "771203"
ALI_N, ALI_I, ALI_S = "770301", "770302", "770303"

# (id, nombre, población, provincia, zona)
EDIFICIOS = [
    ("V01", "DELEGACIÓN ESPECIAL VALENCIA", "Valencia", "Valencia", VAL_N),
    ("V02", "EDIFICIO MESTALLA", "Valencia", "Valencia", VAL_N),
    ("V03", "EDIFICIO JESÚS", "Valencia", "Valencia", VAL_N),
    ("V04", "ADUANA VALENCIA", "Valencia", "Valencia", VAL_N),
    ("V05", "ADUANA VALENCIA (Base Marítima)", "Valencia", "Valencia", VAL_N),
    ("V06", "ADUANA VALENCIA (SCÁNER)", "Valencia", "Valencia", VAL_N),
    ("V07", "ARCHIVO PICAÑA", "Picanya", "Valencia", VAL_N),
    ("V08", "AD BLASCO IBÁÑEZ", "Valencia", "Valencia", VAL_N),
    ("V09", "AD ALZIRA", "Alzira", "Valencia", VAL_S),
    ("V10", "AD CATARROJA", "Catarroja", "Valencia", VAL_N),
    ("V11", "AD GANDÍA", "Gandía", "Valencia", VAL_S),
    ("V12", "AD LLIRIA", "Llíria", "Valencia", VAL_I),
    ("V13", "AD MANISES", "Manises", "Valencia", VAL_N),
    ("V14", "ADUANA MANISES - AEROPUERTO", "Manises", "Valencia", VAL_N),
    ("V15", "AD MONCADA", "Moncada", "Valencia", VAL_N),
    ("V16", "AD REQUENA", "Requena", "Valencia", VAL_I),
    ("V17", "AD SAGUNTO", "Sagunto", "Valencia", VAL_N),
    ("V18", "ADUANA SAGUNTO", "Sagunto", "Valencia", VAL_N),
    ("V19", "AD SUECA", "Sueca", "Valencia", VAL_S),
    ("V20", "AD TORRENT", "Torrent", "Valencia", VAL_N),
    ("V21", "AD XÁTIVA", "Xàtiva", "Valencia", VAL_I),
    ("C01", "DELEGACIÓN CASTELLÓN", "Castellón de la Plana", "Castellón", CAS_S),
    ("C02", "ADUANA CASTELLÓN (Grao)", "Castellón de la Plana", "Castellón", CAS_S),
    ("C03", "ADUANA CASTELLÓN (Base Marítima)", "Castellón de la Plana", "Castellón", CAS_S),
    ("C04", "AD VILA-REAL", "Vila-real", "Castellón", CAS_S),
    ("C05", "AD VINAROZ", "Vinaròs", "Castellón", CAS_N),
    ("A01", "DELEGACIÓN ALICANTE", "Alicante", "Alicante", ALI_S),
    ("A02", "EDIFICIO EUROPA", "Alicante", "Alicante", ALI_S),
    ("A03", "ADUANA ALICANTE - MARÍTIMA", "Alicante", "Alicante", ALI_S),
    ("A04", "ADUANA ALICANTE - CARABINEROS", "Alicante", "Alicante", ALI_S),
    ("A05", "ADUANA ALICANTE - BASE MARÍTIMA", "Alicante", "Alicante", ALI_S),
    ("A06", "ADUANA AEROPUERTO ALICANTE", "El Altet (Elche)", "Alicante", ALI_S),
    ("A07", "ARCHIVO ALICANTE", "Alicante", "Alicante", ALI_S),
    ("A08", "AD ALCOY", "Alcoy", "Alicante", ALI_I),
    ("A09", "AD BENIDORM", "Benidorm", "Alicante", ALI_N),
    ("A10", "AD DENIA", "Dénia", "Alicante", ALI_N),
    ("A11", "AD ELCHE", "Elche", "Alicante", ALI_S),
    ("A12", "AD ELDA", "Elda", "Alicante", ALI_I),
    ("A13", "AD ORIHUELA", "Orihuela", "Alicante", ALI_S),
    ("A14", "AD VILLENA", "Villena", "Alicante", ALI_I),
]

NIVELES = {"Severe": "NARANJA", "Extreme": "ROJO"}


def _get(url):
    req = urllib.request.Request(url, headers={"cache-control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def obtener_avisos():
    if not API_KEY:
        raise SystemExit("Falta la API key: crea un archivo aemet_key.txt junto "
                         "al programa con tu clave, o define AEMET_API_KEY.")
    url = (f"https://opendata.aemet.es/opendata/api/avisos_cap/"
           f"ultimoelaborado/area/{AREA}?api_key={API_KEY}")
    meta = json.loads(_get(url).decode("utf-8"))
    if meta.get("estado") != 200:
        raise SystemExit(f"Error AEMET: {meta.get('descripcion')}")

    contenido = _get(meta["datos"])
    avisos = []
    with tarfile.open(fileobj=io.BytesIO(contenido)) as tar:
        for miembro in tar.getmembers():
            if not miembro.isfile():
                continue
            xml = tar.extractfile(miembro).read()
            avisos.extend(procesar_cap(xml))
    return avisos


def procesar_cap(xml_data):
    root = ET.fromstring(xml_data)
    resultado = []
    for info in root.findall("cap:info", NS):
        lang = info.findtext("cap:language", default="", namespaces=NS)
        if lang and not lang.lower().startswith("es"):
            continue
        nivel = NIVELES.get(info.findtext("cap:severity", default="", namespaces=NS))
        if not nivel:
            continue
        for area in info.findall("cap:area", NS):
            for gc in area.findall("cap:geocode", NS):
                if gc.findtext("cap:valueName", namespaces=NS) == "EMMA_ID":
                    resultado.append({
                        "zona": gc.findtext("cap:value", namespaces=NS),
                        "zona_nombre": area.findtext("cap:areaDesc", default="", namespaces=NS),
                        "nivel": nivel,
                        "fenomeno": info.findtext("cap:event", default="Meteorología adversa", namespaces=NS),
                        "inicio": info.findtext("cap:onset", default=info.findtext("cap:effective", default="", namespaces=NS), namespaces=NS),
                        "fin": info.findtext("cap:expires", default="", namespaces=NS),
                    })
    return resultado


def fmt(fecha):
    try:
        return datetime.fromisoformat(fecha).strftime("%d/%m %H:%M")
    except ValueError:
        return fecha or "N/A"


def main():
    print(f"\n--- MONITOR AEMET · COMUNITAT VALENCIANA [{datetime.now():%Y-%m-%d %H:%M}] ---")
    avisos = obtener_avisos()
    zonas_con_aviso = {a["zona"] for a in avisos}

    alertas = [(e, a) for e in EDIFICIOS for a in avisos if a["zona"] == e[4]]

    if not alertas:
        print("✅ No hay avisos naranja ni rojo que afecten a las sedes.")
    else:
        print(f"⚠️  {len(alertas)} alertas en sedes:\n")
        print(f"{'SEDE':<35} | {'POBLACIÓN':<22} | {'NIVEL':<8} | {'INICIO':<12} | {'FIN':<12} | RIESGO")
        print("-" * 125)
        for e, a in alertas:
            print(f"{e[1]:<35} | {e[2]:<22} | {a['nivel']:<8} | {fmt(a['inicio']):<12} | {fmt(a['fin']):<12} | {a['fenomeno']}")

    # Ayuda para verificar los códigos de zona
    zonas_sedes = {e[4] for e in EDIFICIOS}
    desconocidas = zonas_con_aviso - zonas_sedes
    if desconocidas:
        print("\nℹ️  Zonas con aviso que no están asignadas a ninguna sede "
              "(revisa tu mapeo de zonas):")
        for a in avisos:
            if a["zona"] in desconocidas:
                print(f"   {a['zona']} - {a['zona_nombre']} ({a['nivel']}, {a['fenomeno']})")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        print(e)
    except Exception as e:
        print("Error inesperado:", e)
    finally:
        if getattr(sys, "frozen", False):
            input("\nPulsa Enter para salir...")
