# Versión PostgreSQL

Esta versión conecta el detector de incendios a una base de datos PostgreSQL local con soporte geoespacial mediante PostGIS.

## Requisitos
- PostgreSQL 14+ instalado localmente
- Extensión PostGIS instalada
- Docker instalado (para MQTT)
- Python 3.8+

## Configuración
1. Copia `.env.example` como `.env`
2. Rellena tus credenciales de PostgreSQL
3. Ejecuta `pip install -r requirements.txt`
4. Crea la base de datos y el schema:
   - Corre `setup_database.py` para inicializar todo
   - O ejecuta manualmente `schema.sql` e `init_sensors.sql`

## Uso
Terminal 1: python anomaly_detector_db.py
Terminal 2: python sensor_simulator.py

## Diferencia con la versión Supabase
- Base de datos local, sin necesidad de cuenta en la nube
- Requiere PostgreSQL instalado en tu máquina
- Mayor control sobre la configuración de la base de datos