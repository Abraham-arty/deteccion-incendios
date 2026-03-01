"""
MIGRACIÓN DE SENSORES A SUPABASE
=================================
Inserta los 500 sensores en Supabase (solo ejecutar una vez).
"""

import random
from supabase_manager import SupabaseManager
from dotenv import load_dotenv

load_dotenv()

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

def migrate_sensors():
    """Migra los 500 sensores a Supabase"""
    
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║   MIGRACIÓN DE SENSORES A SUPABASE                   ║
    ║                                                       ║
    ║   Este script insertará 500 sensores                 ║
    ║   Solo ejecutar UNA VEZ                              ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    
    # Conectar a Supabase
    print("\n🔌 Conectando a Supabase...")
    db = SupabaseManager()
    
    if not db.connect():
        print("❌ Error conectando a Supabase")
        return False
    
    # Verificar si ya existen sensores
    try:
        cursor = db.pg_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sensors")
        existing_count = cursor.fetchone()[0]
        cursor.close()
        
        if existing_count > 0:
            print(f"\n⚠️ Ya existen {existing_count} sensores en Supabase")
            response = input("¿Deseas continuar y agregar más? (s/n): ")
            if response.lower() != 's':
                print("❌ Operación cancelada")
                return False
    except Exception as e:
        print(f"⚠️ Error verificando sensores existentes: {e}")
    
    # Generar zonas
    print("\n🌲 Generando 100 zonas forestales...")
    zones = ForestZones.generate_zones(100)
    
    sensor_types = [
        ('temperature', 'celsius'),
        ('humidity', 'percent'),
        ('co2', 'ppm'),
        ('wind_speed', 'kmh'),
        ('wind_direction', 'degrees')
    ]
    
    print(f"🌡️ Insertando 500 sensores (5 por zona)...")
    
    try:
        cursor = db.pg_conn.cursor()
        inserted = 0
        
        for zone in zones:
            for sensor_type, unit in sensor_types:
                sensor_id = f"S_{zone['zone_id']}_{sensor_type[:4]}"
                
                cursor.execute("""
                    INSERT INTO sensors (sensor_id, location, zone_id, region, sensor_type, unit)
                    VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s)
                    ON CONFLICT (sensor_id) DO NOTHING
                """, (
                    sensor_id,
                    zone['lon'],
                    zone['lat'],
                    zone['zone_id'],
                    zone['region'],
                    sensor_type,
                    unit
                ))
                
                inserted += 1
                
                if inserted % 50 == 0:
                    print(f"   ⏳ Progreso: {inserted}/500 sensores...")
        
        db.pg_conn.commit()
        
        # Verificar inserción
        cursor.execute("SELECT COUNT(*) FROM sensors")
        total = cursor.fetchone()[0]
        
        print(f"\n✅ Migración completada!")
        print(f"📊 Total sensores en Supabase: {total}")
        
        # Resumen por región
        cursor.execute("""
            SELECT region, COUNT(*) as count
            FROM sensors
            GROUP BY region
            ORDER BY region
        """)
        
        print("\n🗺️ Distribución por región:")
        for row in cursor.fetchall():
            print(f"   • {row[0]}: {row[1]} sensores")
        
        # Resumen por tipo
        cursor.execute("""
            SELECT sensor_type, COUNT(*) as count
            FROM sensors
            GROUP BY sensor_type
            ORDER BY sensor_type
        """)
        
        print("\n🌡️ Distribución por tipo:")
        for row in cursor.fetchall():
            print(f"   • {row[0]}: {row[1]} sensores")
        
        cursor.close()
        db.disconnect()
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error insertando sensores: {e}")
        db.pg_conn.rollback()
        db.disconnect()
        return False

if __name__ == "__main__":
    try:
        success = migrate_sensors()
        
        if success:
            print("\n" + "="*60)
            print("✅ ¡MIGRACIÓN EXITOSA!")
            print("="*60)
            print("\n📋 Próximos pasos:")
            print("   1. Verifica los datos en Supabase Dashboard")
            print("   2. Ejecuta: docker-compose -f docker-compose-supabase.yml up")
            print("   3. Los datos se guardarán automáticamente en Supabase")
            print("\n🌐 Ahora puedes conectar tu web directamente a Supabase")
        
    except KeyboardInterrupt:
        print("\n\n🛑 Migración cancelada por el usuario")
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()