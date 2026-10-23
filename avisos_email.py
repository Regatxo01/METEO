"""Notificaciones SMTP GMX por cambios de avisos naranjas y rojos.
No publica contraseñas ni guarda direcciones de remitente en el HTML.
"""
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

BASE = Path(__file__).resolve().parent
ESTADO = BASE / "estado_correos.json"
DESTINATARIOS = BASE / "destinatarios.json"


def cargar(path, predeterminado):
    if not path.exists():
        return predeterminado
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def claves_actuales(datos):
    """Una clave por edificio, fenómeno y nivel; cambio de fechas implica nuevo aviso."""
    claves = {}
    for edificio in datos.get("edificios", []):
        for aviso in edificio.get("alertas", []):
            nivel = str(aviso.get("nivel", "")).upper()
            if nivel not in ("NARANJA", "ROJO"):
                continue
            id_edificio = str(edificio.get("id") or edificio.get("nombre", ""))
            fenomeno = str(aviso.get("fenomeno", ""))
            identidad = json.dumps([id_edificio, fenomeno], ensure_ascii=False)
            registro = {
                "edificio": edificio.get("nombre", id_edificio),
                "nivel": nivel, "fenomeno": fenomeno,
                "inicio": aviso.get("inicio", ""), "fin": aviso.get("fin", ""),
            }
            # Evita perder varios avisos del mismo fenómeno si difieren en fechas.
            identidad = json.dumps([id_edificio, fenomeno, registro["inicio"]], ensure_ascii=False)
            claves[identidad] = registro
    return claves


def procesar_avisos(datos):
    usuario = os.getenv("SMTP_USUARIO", "").strip()
    clave = os.getenv("SMTP_CLAVE", "")
    remitente = os.getenv("SMTP_REMITENTE", usuario).strip()
    if not usuario or not clave:
        print("Correos desactivados: faltan SMTP_USUARIO o SMTP_CLAVE; estado sin modificar.")
        return
    contactos = cargar(DESTINATARIOS, {}).get("destinatarios", [])
    correos = sorted({str(x.get("correo", "")).strip() for x in contactos
                      if x.get("activo") and "@" in str(x.get("correo", ""))})
    if not correos:
        print("No hay destinatarios activos; estado sin modificar.")
        return
    anterior = cargar(ESTADO, {"alertas": {}}).get("alertas", {})
    actual = claves_actuales(datos)
    cambios = [(k, v) for k, v in actual.items() if anterior.get(k) != v]
    if cambios:
        msg = EmailMessage()
        msg["From"] = remitente
        msg["To"] = ", ".join(correos)
        msg["Subject"] = f"METEO: {len(cambios)} cambio(s) en alertas naranja/roja"
        lineas = ["Cambios detectados en la última consulta AEMET:", ""]
        for _, a in cambios:
            lineas += [f"Edificio: {a['edificio']}", f"Nivel: {a['nivel']}",
                       f"Fenómeno: {a['fenomeno']}", f"Inicio: {a['inicio']}",
                       f"Fin: {a['fin']}", ""]
        msg.set_content("\n".join(lineas))
        puerto = int(os.getenv("SMTP_PUERTO", "587"))
        if puerto == 465:
            with smtplib.SMTP_SSL("mail.gmx.com", puerto, context=ssl.create_default_context(), timeout=25) as smtp:
                smtp.login(usuario, clave)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP("mail.gmx.com", puerto, timeout=25) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(usuario, clave)
                smtp.send_message(msg)
        print(f"Correo enviado: {len(cambios)} avisos a {len(correos)} destinatarios.")
    else:
        print("Sin cambios naranja/rojo que comunicar.")
    # Solo actualizamos después de enviar con éxito o confirmar que no hay cambios.
    ESTADO.write_text(json.dumps({"alertas": actual}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
