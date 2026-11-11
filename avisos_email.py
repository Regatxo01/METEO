"""Notificaciones SMTP GMX por cambios de avisos naranjas y rojos.
Correo HTML con tablas de alertas actuales y previsión meteorológica de mañana.
La previsión diaria procede de AEMET; no constituye por sí misma un aviso oficial.
"""
import html
import json
import os
import smtplib
import ssl
from datetime import datetime
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


def escapar(valor):
    return html.escape(str(valor if valor not in (None, "") else "—"))


def formatear_duracion(inicio, fin):
    if not inicio or not fin:
        return "—"
    formatos = (
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M%z", "%Y-%m-%dT%H:%M",
        "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M",
    )

    def convertir(valor):
        valor = str(valor).replace("Z", "+00:00")
        for formato in formatos:
            try:
                return datetime.strptime(valor, formato)
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(valor)
        except ValueError:
            return None

    a, b = convertir(inicio), convertir(fin)
    if not a or not b:
        return "—"
    minutos = int((b - a).total_seconds() // 60)
    if minutos < 0:
        return "—"
    dias, resto = divmod(minutos, 1440)
    horas, mins = divmod(resto, 60)
    partes = []
    if dias:
        partes.append(f"{dias} d")
    if horas:
        partes.append(f"{horas} h")
    if mins or not partes:
        partes.append(f"{mins} min")
    return " ".join(partes)


def claves_actuales(datos):
    claves = {}
    for edificio in datos.get("edificios", []):
        for aviso in edificio.get("alertas", []):
            nivel = str(aviso.get("nivel", "")).upper()
            if nivel not in ("NARANJA", "ROJO"):
                continue
            id_edificio = str(edificio.get("id") or edificio.get("nombre", ""))
            fenomeno = str(aviso.get("fenomeno", ""))
            registro = {
                "edificio": edificio.get("nombre", id_edificio),
                "nivel": nivel,
                "fenomeno": fenomeno,
                "inicio": aviso.get("inicio", ""),
                "fin": aviso.get("fin", ""),
            }
            identidad = json.dumps(
                [id_edificio, fenomeno, registro["inicio"]], ensure_ascii=False
            )
            claves[identidad] = registro
    return claves


def estilo_celda(encabezado=False):
    """Estilos en línea y atributos HTML clásicos para máxima compatibilidad email."""
    if encabezado:
        return ' style="border:1px solid #1b2b3b;padding:9px 7px;background-color:#263b53;color:#ffffff;font-family:Arial,sans-serif;font-size:12px;font-weight:bold;text-align:left;"'
    return ' style="border:1px solid #b8c2cc;padding:8px 7px;background-color:#ffffff;color:#263238;font-family:Arial,sans-serif;font-size:12px;text-align:left;vertical-align:top;"'


def construir_tabla(encabezados, filas):
    th = ''.join(f'<th{estilo_celda(True)} bgcolor="#263b53">{h}</th>' for h in encabezados)
    cuerpo = []
    for fila in filas:
        celdas = ''.join(f'<td{estilo_celda(False)}>{valor}</td>' for valor in fila)
        cuerpo.append(f'<tr>{celdas}</tr>')
    return (
        '<table role="table" border="1" cellpadding="0" cellspacing="0" '
        'width="100%" bgcolor="#ffffff" '
        'style="width:100%;border:1px solid #b8c2cc;border-collapse:collapse;'
        'mso-table-lspace:0pt;mso-table-rspace:0pt;font-family:Arial,sans-serif;'
        'font-size:12px;table-layout:auto;">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(cuerpo)}</tbody></table>'
    )


def tabla_alertas(cambios):
    if not cambios:
        return '<p style="color:#555555;font-family:Arial,sans-serif;">No hay alertas naranjas o rojas nuevas o modificadas.</p>'
    filas = []
    for aviso in sorted(cambios, key=lambda x: (x["nivel"] != "ROJO", x["edificio"])):
        color = "#c62828" if aviso["nivel"] == "ROJO" else "#ef6c00"
        nivel = f'<strong style="color:{color};">{escapar(aviso["nivel"])}</strong>'
        filas.append([
            escapar(aviso["edificio"]), escapar(aviso["fenomeno"]), nivel,
            escapar(aviso["inicio"]), escapar(aviso["fin"]),
            escapar(formatear_duracion(aviso["inicio"], aviso["fin"])),
        ])
    return construir_tabla(
        ["Edificio", "Fenómeno", "Nivel", "Inicio", "Finalización", "Duración"], filas
    )


def tabla_prevision(datos):
    previsiones = datos.get("prevision_manana") or []
    if not previsiones:
        return (
            '<p style="padding:10px;background-color:#f3f5f7;border:1px solid #cfd8dc;'
            'font-family:Arial,sans-serif;">Previsión para mañana no disponible para los edificios en esta consulta.</p>'
        )
    filas = []
    for item in previsiones:
        lluvia = item.get("lluvia")
        lluvia_txt = f"{lluvia} %" if lluvia is not None else "—"
        max_txt = f'{item["max"]} °C' if item.get("max") is not None else "—"
        min_txt = f'{item["min"]} °C' if item.get("min") is not None else "—"
        filas.append([
            escapar(item.get("edificio")), escapar(item.get("estado")),
            escapar(max_txt), escapar(min_txt), escapar(lluvia_txt),
        ])
    return construir_tabla(
        ["Edificio", "Previsión", "Máxima", "Mínima", "Prob. lluvia"], filas
    )


def crear_html(datos, cambios):
    fecha = escapar(datos.get("fecha", ""))
    rojas = sum(1 for _, aviso in cambios if aviso["nivel"] == "ROJO")
    naranjas = sum(1 for _, aviso in cambios if aviso["nivel"] == "NARANJA")
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:20px;background:#f2f4f7;font-family:Arial,sans-serif;color:#263238">
<div style="max-width:1000px;margin:auto;background:#fff;padding:22px;border:1px solid #dce1e6">
<table role="presentation" border="0" cellpadding="0" cellspacing="0" style="margin:0 0 18px"><tr><td align="center" bgcolor="#2563eb" style="background:#2563eb;border-radius:6px"><a href="https://regatxo01.github.io/METEO/" target="_blank" style="display:inline-block;padding:13px 22px;color:#ffffff;text-decoration:none;font-weight:bold;font-family:Arial,sans-serif;font-size:15px">ABRIR PROGRAMA METEO</a></td></tr></table>
<p style="margin:0 0 18px;font-size:12px;color:#607d8b">Si no puedes pulsar el botón, abre este enlace: <a href="https://regatxo01.github.io/METEO/" style="color:#2563eb">https://regatxo01.github.io/METEO/</a></p>
<h2 style="margin:0 0 5px;color:#263b53">METEO · INFORME DE ALERTAS</h2>
<p style="margin:0 0 18px;color:#607d8b;font-size:13px">Consulta: {fecha}</p>
<table role="presentation" border="0" cellpadding="8" cellspacing="0" width="100%" style="width:100%;border-collapse:collapse;margin-bottom:22px"><tr>
<td style="background:#ffebee;border:1px solid #ffcdd2"><b style="color:#c62828;font-size:22px">{rojas}</b><br>Alertas rojas nuevas/modificadas</td>
<td style="background:#fff3e0;border:1px solid #ffe0b2"><b style="color:#ef6c00;font-size:22px">{naranjas}</b><br>Alertas naranjas nuevas/modificadas</td>
<td style="background:#eceff1;border:1px solid #cfd8dc"><b style="font-size:22px">{len(cambios)}</b><br>Cambios comunicados</td>
</tr></table>
<h3 style="color:#263b53">1. Alertas actuales</h3>
{tabla_alertas([aviso for _, aviso in cambios])}
<h3 style="margin-top:28px;color:#263b53">2. Previsión para el día siguiente</h3>
{tabla_prevision(datos)}
<p style="margin-top:24px;color:#78909c;font-size:11px">
Previsión meteorológica diaria de AEMET. La predicción no constituye por sí misma un aviso oficial.
</p>
<table role="presentation" border="0" cellpadding="0" cellspacing="0" style="margin:22px 0 0"><tr><td align="center" bgcolor="#2563eb" style="background:#2563eb;border-radius:6px"><a href="https://regatxo01.github.io/METEO/" target="_blank" style="display:inline-block;padding:13px 22px;color:#ffffff;text-decoration:none;font-weight:bold;font-family:Arial,sans-serif;font-size:15px">ABRIR PROGRAMA METEO</a></td></tr></table>
<p style="margin:8px 0 0;font-size:12px;color:#607d8b"><a href="https://regatxo01.github.io/METEO/" style="color:#2563eb">https://regatxo01.github.io/METEO/</a></p>
</div></body></html>"""


def procesar_avisos(datos):
    usuario = os.getenv("SMTP_USUARIO", "").strip()
    clave = os.getenv("SMTP_CLAVE", "")
    remitente = os.getenv("SMTP_REMITENTE", "").strip() or usuario
    if not usuario or not clave:
        print("Correos desactivados: faltan SMTP_USUARIO o SMTP_CLAVE; estado sin modificar.")
        return

    contactos = cargar(DESTINATARIOS, {}).get("destinatarios", [])
    correos = sorted({
        str(x.get("correo", "")).strip()
        for x in contactos
        if x.get("activo") and "@" in str(x.get("correo", ""))
    })
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
        for _, aviso in cambios:
            lineas.extend([
                f"Edificio: {aviso['edificio']}", f"Nivel: {aviso['nivel']}",
                f"Fenómeno: {aviso['fenomeno']}", f"Inicio: {aviso['inicio']}",
                f"Finalización: {aviso['fin']}",
                f"Duración: {formatear_duracion(aviso['inicio'], aviso['fin'])}", ""
            ])
        lineas.append("Previsión para mañana (AEMET):")
        previsiones = datos.get("prevision_manana") or []
        if previsiones:
            for p in previsiones:
                lineas.append(
                    f"{p.get('edificio', '—')}: {p.get('estado', '—')} | "
                    f"Máx. {p.get('max', '—')} °C | Mín. {p.get('min', '—')} °C | "
                    f"Prob. lluvia {p.get('lluvia', '—')} %"
                )
        else:
            lineas.append("No disponible.")
        # HTML como cuerpo principal: evita que el cliente móvil muestre
        # la alternativa de texto plano en lugar de las tablas.
        msg.set_content(crear_html(datos, cambios), subtype="html", charset="utf-8")

        puerto = int(os.getenv("SMTP_PUERTO", "587"))
        if puerto == 465:
            with smtplib.SMTP_SSL(
                "mail.gmx.com", puerto,
                context=ssl.create_default_context(), timeout=25
            ) as smtp:
                smtp.login(usuario, clave)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP("mail.gmx.com", puerto, timeout=25) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(usuario, clave)
                smtp.send_message(msg)
        print(f"Correo enviado: {len(cambios)} cambios a {len(correos)} destinatarios.")
    else:
        print("Sin cambios naranja/rojo que comunicar.")

    ESTADO.write_text(
        json.dumps({"alertas": actual}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    # Pequeña prueba local de generación de HTML, sin enviar correo.
    print("Módulo de correo METEO cargado correctamente.")
