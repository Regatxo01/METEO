"""Simula avisos NARANJA y ROJO con estado aislado; no consulta AEMET."""
import tempfile
from pathlib import Path
import avisos_email


def datos(nivel):
    return {"edificios": [{
        "id": "SIMULACION-METEO", "nombre": "EDIFICIO DE PRUEBA (SIMULACIÓN)",
        "alertas": [{"nivel": nivel, "fenomeno": "Viento fuerte - SIMULACIÓN, NO ES ALERTA REAL",
                     "inicio": "01/01/2030 10:00", "fin": "01/01/2030 18:00"}]
    }]}


def main():
    estado_real = avisos_email.ESTADO
    with tempfile.TemporaryDirectory(prefix="meteo_simulacion_") as carpeta:
        avisos_email.ESTADO = Path(carpeta) / "estado_prueba.json"
        try:
            print("PRUEBA 1: Nueva alerta NARANJA. Se enviará un correo de simulación.")
            avisos_email.procesar_avisos(datos("NARANJA"))
            print("PRUEBA 2: Misma alerta NARANJA. No debe enviar otro correo.")
            antes = avisos_email.ESTADO.read_text(encoding="utf-8")
            avisos_email.procesar_avisos(datos("NARANJA"))
            assert avisos_email.ESTADO.read_text(encoding="utf-8") == antes
            print("PRUEBA 3: Cambio de NARANJA a ROJO. Se enviará otro correo de simulación.")
            avisos_email.procesar_avisos(datos("ROJO"))
            print("PRUEBAS FINALIZADAS. Comprueba los dos correos recibidos.")
        finally:
            avisos_email.ESTADO = estado_real


if __name__ == "__main__":
    main()
