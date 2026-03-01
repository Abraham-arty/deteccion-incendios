"""
SETUP DE BASE DE DATOS POSTGRESQL
==================================
Script para inicializar la base de datos del sistema de detección de incendios.

FUNCIONES:
1. Crear la base de datos
2. Ejecutar el schema.sql
3. Insertar los 500 sensores iniciales
4. Verificar la instalación

REQUISITOS:
- PostgreSQL instalado y corriendo
- Credenciales de superusuario o usuario con permisos
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv
import sys
import os

load_dotenv()

# ============================================
# CONFIGURACIÓN DE CONEXIÓN (desde variables de entorno)
# ============================================
DB_CONFIG = {
    'host': os.getenv('PG_HOST', 'localhost'),
    'port': int(os.getenv('PG_PORT', 5432)),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD'),
    'database': os.getenv('PG_DATABASE', 'postgres')
}

ADMIN_CONFIG = DB_CONFIG.copy()

# ============================================
# GENERADOR DE ZONAS (igual que en simulador)
# ============================================
class ForestZones:
    """Regiones forestales de México con coordenadas reales"""
    
    REGIONS = {
        'Durango': {'lat_min': 24.0, 'lat_max': 25.5, 'lon_min': -105.5, 'lon_max': -104.0},
        'Chihuahua': {'lat_min': 27.0, 'lat_max': 29.0, 'lon_min': -108.0, 'lon_max': -106.0},
        'Jalisco': {'lat_min': 19.5, 'lat_max': 21.0, 'lon_min': -104.5, 'lon_max': -103.0},
        'Michoacán': {'lat_min': 18.5, 'lat_max': 20.0, 'lon_min': -103.0, 'lon_max': -101.0},
        'Oaxaca': {'lat_min': 16.0, 'lat_max': 18.0, 'lon_min': -97.5, 'lon_max': -95.5}
    }
    
    @staticmethod
    def generate_zones(num_zones=100):
        """Genera coordenadas para N zonas"""
        import random
        zones = []
        regions_list = list(ForestZones.REGIONS.items())
        zones_per_region = num_zones // len(regions_list)
        
        zone_id = 1
        for region_name, bounds in regions_list:
            for _ in range(zones_per_region):
                lat = random.uniform(bounds['lat_min'], bounds['lat_max'])
                lon = random.uniform(bounds['lon_min'], bounds['lon_max'])
                
                zones.append({
                    'zone_id': f'Z_{zone_id:03d}',
                    'region': region_name,
                    'lat': round(lat, 6),
                    'lon': round(lon, 6)
                })
                zone_id += 1
        
        # Completar hasta 100
        while len(zones) < num_zones:
            region_name, bounds = random.choice(regions_list)
            lat = random.uniform(bounds['lat_min'], bounds['lat_max'])
            lon = random.uniform(bounds['lon_min'], bounds['lon_max'])
            
            zones.append({
                'zone_id': f'Z_{zone_id:03d}',
                'region': region_name,
                'lat': round(lat, 6),
                'lon': round(lon, 6)
            })
            zone_id += 1
        
        return zones

# ============================================
# FUNCIONES DE SETUP
# ============================================

def create_database():
    """Crea la base de datos fire_detection si no existe"""
    try:
        print("\n🔧 Conectando como administrador...")
        conn = psycopg2.connect(**ADMIN_CONFIG)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Verificar si existe
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'fire_detection'")
        exists = cursor.fetchone()
        
        if exists:
            print("✅ Base de datos 'fire_detection' ya existe")
        else:
            print("📦 Creando base de datos 'fire_detection'...")
            cursor.execute("CREATE DATABASE fire_detection")
            print("✅ Base de datos creada exitosamente")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Error creando base de datos: {e}")
        return False

def create_user():
    """Crea el usuario fireuser si no existe"""
    try:
        conn = psycopg2.connect(**ADMIN_CONFIG)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Verificar si existe
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = 'fireuser'")
        exists = cursor.fetchone()
        
        if exists:
            print("✅ Usuario 'fireuser' ya existe")
        else:
            print("👤 Creando usuario 'fireuser'...")
            cursor.execute(f"CREATE USER fireuser WITH PASSWORD '{DB_CONFIG['password']}'")
            print("✅ Usuario creado exitosamente")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Error creando usuario: {e}")
        return False

def execute_schema():
    """Ejecuta el archivo schema.sql"""
    try:
        print("\n📄 Ejecutando schema.sql...")
        
        # Leer archivo SQL
        if not os.path.exists('schema.sql'):
            print("❌ Archivo schema.sql no encontrado")
            print("💡 Asegúrate de que schema.sql esté en el mismo directorio")
            return False
        
        with open('schema.sql', 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        # Conectar y ejecutar
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute(schema_sql)
        conn.commit()
        
        print("✅ Schema ejecutado exitosamente")
        
        # Verificar tablas creadas
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        print(f"\n📊 Tablas creadas ({len(tables)}):")
        for table in tables:
            print(f"   • {table[0]}")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Error ejecutando schema: {e}")
        return False
    except FileNotFoundError:
        print(f"❌ Archivo schema.sql no encontrado")
        return False

def insert_sensors():
    """Inserta los 500 sensores en la tabla sensors"""
    try:
        print("\n🌡️  Insertando 500 sensores...")
        
        # Generar zonas
        zones = ForestZones.generate_zones(100)
        
        sensor_types = [
            ('temperature', 'celsius'),
            ('humidity', 'percent'),
            ('co2', 'ppm'),
            ('wind_speed', 'kmh'),
            ('wind_direction', 'degrees')
        ]
        
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        sensor_count = 0
        
        # Insertar sensores para cada zona
        for zone in zones:
            for sensor_type, unit in sensor_types:
                sensor_id = f"S_{zone['zone_id']}_{sensor_type[:4]}"
                
                # Usar PostGIS para crear punto geográfico
                cursor.execute("""
                    INSERT INTO sensors (sensor_id, location, zone_id, region, sensor_type, unit)
                    VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s)
                    ON CONFLICT (sensor_id) DO NOTHING
                """, (
                    sensor_id,
                    zone['lon'],  # Longitud primero en PostGIS
                    zone['lat'],  # Latitud segundo
                    zone['zone_id'],
                    zone['region'],
                    sensor_type,
                    unit
                ))
                
                sensor_count += 1
        
        conn.commit()
        
        # Verificar inserción
        cursor.execute("SELECT COUNT(*) FROM sensors")
        total = cursor.fetchone()[0]
        
        print(f"✅ {total} sensores insertados exitosamente")
        
        # Mostrar resumen por región
        cursor.execute("""
            SELECT region, COUNT(*) as count
            FROM sensors
            GROUP BY region
            ORDER BY region
        """)
        
        print("\n📍 Sensores por región:")
        for row in cursor.fetchall():
            print(f"   • {row[0]}: {row[1]} sensores")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Error insertando sensores: {e}")
        return False

def verify_installation():
    """Verifica que todo esté correctamente instalado"""
    try:
        print("\n🔍 Verificando instalación...")
        
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Verificar extensión PostGIS
        cursor.execute("SELECT PostGIS_version()")
        postgis_version = cursor.fetchone()[0]
        print(f"✅ PostGIS instalado: {postgis_version}")
        
        # Verificar tablas
        required_tables = [
            'sensors', 'readings', 'fire_incidents', 
            'fire_analysis', 'system_stats', 'alert_log'
        ]
        
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
                AND table_name IN %s
        """, (tuple(required_tables),))
        
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        print(f"\n📋 Verificación de tablas:")
        for table in required_tables:
            if table in existing_tables:
                print(f"   ✅ {table}")
            else:
                print(f"   ❌ {table} - NO ENCONTRADA")
        
        # Verificar sensores
        cursor.execute("SELECT COUNT(*) FROM sensors")
        sensor_count = cursor.fetchone()[0]
        
        if sensor_count == 500:
            print(f"\n✅ Sensores: {sensor_count}/500")
        else:
            print(f"\n⚠️  Sensores: {sensor_count}/500 (esperados 500)")
        
        cursor.close()
        conn.close()
        
        return len(existing_tables) == len(required_tables) and sensor_count == 500
        
    except psycopg2.Error as e:
        print(f"❌ Error verificando instalación: {e}")
        return False

def test_connection():
    """Prueba la conexión a la base de datos"""
    try:
        print("\n🔌 Probando conexión a PostgreSQL...")
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        print(f"✅ Conexión exitosa")
        print(f"   PostgreSQL: {version.split(',')[0]}")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.OperationalError:
        print(f"❌ No se pudo conectar a PostgreSQL")
        print(f"\n💡 Verifica que:")
        print(f"   1. PostgreSQL esté corriendo")
        print(f"   2. Las credenciales sean correctas:")
        print(f"      Host: {DB_CONFIG['host']}")
        print(f"      Port: {DB_CONFIG['port']}")
        print(f"      User: {DB_CONFIG['user']}")
        print(f"      Database: {DB_CONFIG['database']}")
        return False

# ============================================
# MAIN
# ============================================
def main():
    print("""
    ╔════════════════════════════════════════════════════════╗
    ║   SETUP DE BASE DE DATOS - SISTEMA DETECCIÓN INCENDIOS║
    ║                                                        ║
    ║   Este script:                                         ║
    ║   1. Crea la base de datos fire_detection            ║
    ║   2. Ejecuta el schema.sql                            ║
    ║   3. Inserta 500 sensores                             ║
    ║   4. Verifica la instalación                          ║
    ╚════════════════════════════════════════════════════════╝
    """)
    
    print("\n⚙️  CONFIGURACIÓN ACTUAL:")
    print(f"   Host: {DB_CONFIG['host']}")
    print(f"   Port: {DB_CONFIG['port']}")
    print(f"   User: {DB_CONFIG['user']}")
    print(f"   Database: {DB_CONFIG['database']}")
    
    response = input("\n¿La configuración es correcta? (s/n): ")
    if response.lower() != 's':
        print("\n💡 Edita el archivo setup_database.py y modifica DB_CONFIG")
        sys.exit(0)
    
    # Paso 1: Crear usuario (como admin)
    print("\n" + "="*60)
    print("PASO 1: CREAR USUARIO")
    print("="*60)
    if not create_user():
        print("\n⚠️  Advertencia: No se pudo crear usuario (puede que ya exista)")
    
    # Paso 2: Crear base de datos
    print("\n" + "="*60)
    print("PASO 2: CREAR BASE DE DATOS")
    print("="*60)
    if not create_database():
        print("\n❌ No se pudo crear la base de datos")
        sys.exit(1)
    
    # Paso 3: Probar conexión
    print("\n" + "="*60)
    print("PASO 3: PROBAR CONEXIÓN")
    print("="*60)
    if not test_connection():
        print("\n❌ No se pudo conectar a la base de datos")
        sys.exit(1)
    
    # Paso 4: Ejecutar schema
    print("\n" + "="*60)
    print("PASO 4: EJECUTAR SCHEMA")
    print("="*60)
    if not execute_schema():
        print("\n❌ No se pudo ejecutar el schema")
        sys.exit(1)
    
    # Paso 5: Insertar sensores
    print("\n" + "="*60)
    print("PASO 5: INSERTAR SENSORES")
    print("="*60)
    if not insert_sensors():
        print("\n❌ No se pudieron insertar los sensores")
        sys.exit(1)
    
    # Paso 6: Verificar
    print("\n" + "="*60)
    print("PASO 6: VERIFICACIÓN FINAL")
    print("="*60)
    if verify_installation():
        print("\n" + "="*60)
        print("✅ ¡INSTALACIÓN COMPLETADA EXITOSAMENTE!")
        print("="*60)
        print("\n📋 Próximos pasos:")
        print("   1. Ejecutar: python anomaly_detector_db.py")
        print("   2. Ejecutar: python sensor_simulator.py")
        print("   3. Los datos se guardarán automáticamente en PostgreSQL")
    else:
        print("\n⚠️  La instalación se completó con advertencias")
        print("   Revisa los errores arriba")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Setup cancelado por el usuario")
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()