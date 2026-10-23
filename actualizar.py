"""Generación no interactiva del mapa de avisos para GitHub Actions."""
import os
import shutil

if not os.environ.get("AEMET_API_KEY", "").strip():
    raise RuntimeError("Falta el secreto AEMET_API_KEY en GitHub Actions")

import alertas_cp

# No abrir navegador en un servidor remoto.
alertas_cp.abrir_archivo = lambda path: print("Mapa generado:", path)
datos = alertas_cp.main()
from avisos_email import procesar_avisos
procesar_avisos(datos)
shutil.copyfile("alertas_edificios.html", "index.html")
print("index.html actualizado correctamente")
