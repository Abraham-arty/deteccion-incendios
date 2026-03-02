# Versión Supabase

Esta versión conecta el detector de incendios a Supabase como base de datos en la nube.

## Requisitos
- Cuenta en Supabase (supabase.com)
- Docker instalado
- Python 3.8+

## Configuración
1. Copia `.env.example` como `.env`
2. Rellena tus credenciales de Supabase
3. Ejecuta `pip install -r requirements.txt`

## Uso
Terminal 1: python anomaly_detector_supabase.py
Terminal 2: python sensor_simulator.py