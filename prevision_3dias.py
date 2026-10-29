"""Predicción diaria Open-Meteo (no es un aviso oficial AEMET)."""
import json
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

CODIGOS = {0:'Despejado',1:'Poco nuboso',2:'Parcialmente nuboso',3:'Cubierto',45:'Niebla',48:'Niebla helada',51:'Llovizna',53:'Llovizna',55:'Llovizna intensa',56:'Llovizna helada',57:'Llovizna helada',61:'Lluvia débil',63:'Lluvia',65:'Lluvia intensa',66:'Lluvia helada',67:'Lluvia helada',71:'Nieve débil',73:'Nieve',75:'Nieve intensa',77:'Granizo',80:'Chubascos',81:'Chubascos',82:'Chubascos fuertes',85:'Nieve',86:'Nieve intensa',95:'Tormenta',96:'Tormenta y granizo',99:'Tormenta y granizo'}

def consultar(edificios):
    cache = {}
    errores = 0
    for e in edificios:
        if e.get('lat') is None or e.get('lon') is None:
            e['prevision'] = []
            continue
        key = (round(e['lat'], 2), round(e['lon'], 2))
        if key not in cache:
            params = urllib.parse.urlencode({'latitude':key[0], 'longitude':key[1], 'daily':'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max', 'timezone':'Europe/Madrid', 'forecast_days':3})
            try:
                req = urllib.request.Request('https://api.open-meteo.com/v1/forecast?' + params, headers={'User-Agent':'METEO-Edificios/1.0'})
                with urllib.request.urlopen(req, timeout=12) as r:
                    diario = json.load(r)['daily']
                cache[key] = [{'fecha':diario['time'][i], 'estado':CODIGOS.get(diario['weather_code'][i], 'Variable'), 'max':diario['temperature_2m_max'][i], 'min':diario['temperature_2m_min'][i], 'lluvia':diario['precipitation_probability_max'][i]} for i in range(min(3,len(diario['time'])))]
            except Exception as exc:
                print('Predicción no disponible para',key, str(exc)[:120]); cache[key] = []; errores += 1
        e['prevision'] = cache[key]
    print('Predicción de tres días:',len(cache),'ubicaciones;',errores,'errores')
