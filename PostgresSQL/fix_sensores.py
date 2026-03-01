"""
SCRIPT PARA COMPLETAR SENSORES FALTANTES
=========================================
Verifica cuántos sensores hay y completa hasta 500
"""

import psycopg2
import random
from dotenv import load_dotenv
import os

load_dotenv()

# ============================================
# CONFIGURACIÓN (desde variables de entorno)
# ============================================
DB_CONFIG = {
    'host': os.getenv('PG_HOST', 'localhost'),
    'port': int(os.getenv('PG_PORT', 5432)),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD'),
    'database': os.getenv('PG_DATABASE', 'postgres'),
    'client_encoding': 'utf8'
}

class ForestZones:
    """Generador de zonas forestales"""
    
    REGIONS = {
        'Durango': {'lat_min': 24.0, 'lat_max': 25.5, 'lon_min': -105.5, 'lon_max': -104.0},
        'Chihuahua': {'lat_min': 27.0, 'lat_max': 29.0, 'lon_min': -108.0, 'lon_max': -106.0},
        'Jalisco': {'lat_min': 19.5, 'lat_max': 21.0, 'lon_min': -104.5, 'lon_max': -103.0},
        'Michoacán': {'lat_min': 18.5, 'lat_max': 20.0, 'lon_min': -103.0, 'lon_max': -101.0},
        'Oaxaca': {'lat_min': 16.0, 'lat_max': 18.0, 'lon_min': -97.5, 'lon_max': -95.5}
    }
    
    @staticmethod
    def generate_zones(num_zones=100):
        """Genera exactamente N zonas"""
        zones = []
        regions_list = list(ForestZones.REGIONS.items())
        
        # Distribuir uniformemente
        for i in range(num_zones):
            region_name, bounds = regions_list[i % len(regions_list)]
            
            lat = random.uniform(bounds['lat_min'], bounds['lat_max'])
            lon = random.uniform(bounds['lon_min'], bounds['lon_max'])
            
            zones.append({
                'zone_id': f'Z_{(i+1):03d}',
                'region': region_name,
                'lat': round(lat, 6),
                'lon': round(lon, 6)
            })
        
        return zones

def fix_sensors():
    """Verifica y completa sensores faltantes"""
    
    try:
        print("🔍 Conectando a la base de datos...")
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Verificar cuántos sensores hay
        cursor.execute("SELECT COUNT(*) FROM sensors")
        current_count = cursor.fetchone()[0]
        
        print(f"📊 Sensores actuales: {current_count}")
        
        # Verificar qué tipos de sensores existen
        cursor.execute("SELECT DISTINCT sensor_type FROM sensors ORDER BY sensor_type")
        existing_types = [row[0] for row in cursor.fetchall()]
        print(f"🌡️  Tipos existentes: {existing_types}")
        
        # Obtener todas las zonas existentes con su ubicación
        cursor.execute("""
            SELECT DISTINCT zone_id, region, 
                   ST_X(location::geometry) as lon, 
                   ST_Y(location::geometry) as lat
            FROM sensors 
            ORDER BY zone_id
        """)
        existing_zones = cursor.fetchall()
        
        print(f"📍 Zonas existentes: {len(existing_zones)}")
        
        # Tipos de sensores que deberían existir
        all_sensor_types = [
            ('temperature', 'celsius'),
            ('humidity', 'percent'),
            ('co2', 'ppm'),
            ('wind_speed', 'kmh'),
            ('wind_direction', 'degrees')
        ]
        
        inserted = 0
        
        print(f"\n🔧 Insertando sensores faltantes...")
        
        # Para cada zona existente
        for zone_row in existing_zones:
            zone_id = zone_row[0]
            region = zone_row[1]
            lon = zone_row[2]
            lat = zone_row[3]
            
            # Verificar cada tipo de sensor
            for sensor_type, unit in all_sensor_types:
                sensor_id = f"S_{zone_id}_{sensor_type[:4]}"
                
                # Verificar si ya existe
                cursor.execute("SELECT 1 FROM sensors WHERE sensor_id = %s", (sensor_id,))
                exists = cursor.fetchone()
                
                if not exists:
                    # Insertar sensor faltante
                    cursor.execute("""
                        INSERT INTO sensors (sensor_id, location, zone_id, region, sensor_type, unit)
                        VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s)
                    """, (
                        sensor_id,
                        lon,
                        lat,
                        zone_id,
                        region,
                        sensor_type,
                        unit
                    ))
                    inserted += 1
                    print(f"   ✅ Insertado: {sensor_id}")
        
        conn.commit()
        
        # Verificar resultado final
        cursor.execute("SELECT COUNT(*) FROM sensors")
        final_count = cursor.fetchone()[0]
        
        print(f"\n✅ Sensores insertados: {inserted}")
        print(f"📊 Total final de sensores: {final_count}")
        
        if final_count == 500:
            print("🎉 ¡Perfecto! Ahora tienes exactamente 500 sensores")
        elif final_count > 500:
            print(f"⚠️  Hay {final_count - 500} sensores de más")
        else:
            print(f"⚠️  Aún faltan {500 - final_count} sensores")
        
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
        
        # Mostrar resumen por tipo
        cursor.execute("""
            SELECT sensor_type, COUNT(*) as count
            FROM sensors
            GROUP BY sensor_type
            ORDER BY sensor_type
        """)
        
        print("\n🌡️  Sensores por tipo:")
        for row in cursor.fetchall():
            print(f"   • {row[0]}: {row[1]} sensores")
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"❌ Error de base de datos: {e}")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════╗
    ║   CORRECCIÓN DE SENSORES FALTANTES                ║
    ║                                                    ║
    ║   Este script completará los sensores hasta 500   ║
    ╚════════════════════════════════════════════════════╝
    """)
    
    fix_sensors()
    
    print("\n" + "="*60)
    print("✅ Script completado")
    print("="*60)
    print("\n📋 Próximos pasos:")
    print("   1. Verifica que ahora tengas 500 sensores")
    print("   2. Ejecuta: python anomaly_detector_db.py")
    print("   3. Ejecuta: python sensor_simulator.py")