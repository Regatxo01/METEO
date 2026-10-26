"""Prueba manual SMTP de GMX sin consultar AEMET ni alterar estado de alertas."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from avisos_email import cargar, DESTINATARIOS


def main():
    usuario = os.getenv('SMTP_USUARIO', '').strip()
    clave = os.getenv('SMTP_CLAVE', '')
    remitente = os.getenv('SMTP_REMITENTE', '').strip() or usuario
    if not usuario or not clave:
        raise RuntimeError('Faltan los secretos SMTP_USUARIO o SMTP_CLAVE')
    contactos = cargar(DESTINATARIOS, {}).get('destinatarios', [])
    correos = sorted({str(x.get('correo', '')).strip() for x in contactos
                      if x.get('activo') is True and '@' in str(x.get('correo', ''))})
    if not correos:
        raise RuntimeError('No hay destinatarios activos en destinatarios.json')
    msg = EmailMessage()
    msg['From'] = remitente
    msg['To'] = ', '.join(correos)
    msg['Subject'] = 'METEO - Prueba de correo GMX'
    msg.set_content('Este es un mensaje de prueba de METEO.\n'
                    'El envío SMTP desde GitHub Actions está funcionando.\n'
                    'No es una alerta meteorológica real.\n')
    puerto = int(os.getenv('SMTP_PUERTO', '587'))
    if puerto == 465:
        with smtplib.SMTP_SSL('mail.gmx.com', puerto, context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(usuario, clave)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP('mail.gmx.com', puerto, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(usuario, clave)
            smtp.send_message(msg)
    print(f'Prueba SMTP enviada correctamente a {len(correos)} destinatario(s) activo(s).')


if __name__ == '__main__':
    main()
