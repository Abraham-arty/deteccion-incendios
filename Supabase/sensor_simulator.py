"""
SIMULADOR DE 100 SENSORES FORESTALES - VERSIÓN ESCALADA
========================================================
Simula 100 ubicaciones forestales en México, cada una con 5 sensores:
- Temperatura (°C)
- Humedad relativa (%)
- CO2/CO (ppm)
- Velocidad del viento (km/h)
- Dirección del viento (grados 0-360)

CARACTERÍSTICAS:
- Coordenadas geográficas reales de zonas forestales
- 90% datos normales, 10% con anomalías
- Simulación de 2-5 incendios simultáneos
- Evolución gradual de incendios (temperatura sube, humedad baja)
- Publicación vía MQTT
"""

import json
import time
import random
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
import numpy as np
import os

# ============================================
# CONFIGURACIÓN MQTT
# ============================================
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_TOPIC = os.getenv('MQTT_TOPIC', 'sensores/forestales')
CYCLE_INTERVAL = int(os.getenv('CYCLE_INTERVAL', 30))  # segundos


# ============================================
# CONFIGURACIÓN DE ZONAS FORESTALES
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
        """Genera coordenadas para N zonas distribuidas en las regiones"""
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
        
        # Completar hasta 100 si faltan
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
# RANGOS NORMALES DE SENSORES
# ============================================
class SensorRanges:
    """Rangos normales y anómalos según el documento"""
    
    TEMPERATURE = {
        'normal': (15, 35),      # °C
        'anomaly': (45, 65),     # >45°C indica incendio
        'unit': 'celsius'
    }
    
    HUMIDITY = {
        'normal': (40, 80),      # %
        'anomaly': (15, 25),     # <30% indica sequedad extrema
        'unit': 'percent'
    }
    
    CO2 = {
        'normal': (400, 600),    # ppm
        'anomaly': (1200, 2000), # >1000 ppm indica combustión
        'unit': 'ppm'
    }
    
    WIND_SPEED = {
        'normal': (0, 25),       # km/h
        'anomaly': (40, 70),     # >40 km/h propagación rápida
        'unit': 'kmh'
    }
    
    WIND_DIRECTION = {
        'normal': (0, 360),      # grados
        'unit': 'degrees'
    }

# ============================================
# GESTOR DE INCENDIOS
# ============================================
class FireManager:
    """Gestiona qué zonas tienen incendios activos y su evolución"""
    
    def __init__(self, total_zones):
        self.total_zones = total_zones
        self.active_fires = {}  # {zone_id: fire_state}
        self.fire_probability = 0.001  # Probabilidad de nuevo incendio por zona
        
    def update_fires(self):
        """Actualiza el estado de los incendios cada iteración"""
        
        # Iniciar nuevos incendios aleatorios (2-5% de zonas con fuego)
        if len(self.active_fires) < int(self.total_zones * 0.05):
            if random.random() < self.fire_probability * 100:  # Boost inicial
                zone_id = f'Z_{random.randint(1, self.total_zones):03d}'
                if zone_id not in self.active_fires:
                    self.active_fires[zone_id] = {
                        'stage': 'inicio',  # inicio -> desarrollo -> intenso
                        'iterations': 0,
                        'temp_offset': 0,
                        'humidity_offset': 0,
                        'co2_offset': 0,
                        'wind_boost': 0
                    }
        
        # Evolucionar incendios existentes
        zones_to_remove = []
        for zone_id, fire_state in self.active_fires.items():
            fire_state['iterations'] += 1
            
            # Evolución gradual según iteraciones
            if fire_state['iterations'] < 20:
                fire_state['stage'] = 'inicio'
                fire_state['temp_offset'] += random.uniform(1, 3)
                fire_state['humidity_offset'] -= random.uniform(2, 5)
                fire_state['co2_offset'] += random.uniform(50, 100)
                fire_state['wind_boost'] += random.uniform(1, 3)
                
            elif fire_state['iterations'] < 50:
                fire_state['stage'] = 'desarrollo'
                fire_state['temp_offset'] += random.uniform(0.5, 2)
                fire_state['humidity_offset'] -= random.uniform(1, 3)
                fire_state['co2_offset'] += random.uniform(30, 80)
                
            elif fire_state['iterations'] < 80:
                fire_state['stage'] = 'intenso'
                # Mantener valores altos con variación
                fire_state['temp_offset'] = max(30, fire_state['temp_offset'] + random.uniform(-2, 2))
                fire_state['humidity_offset'] = min(-30, fire_state['humidity_offset'] + random.uniform(-2, 2))
                fire_state['co2_offset'] = max(1000, fire_state['co2_offset'] + random.uniform(-50, 50))
                
            else:
                # Incendio controlado, remover
                zones_to_remove.append(zone_id)
        
        # Limpiar incendios terminados
        for zone_id in zones_to_remove:
            del self.active_fires[zone_id]
    
    def is_zone_on_fire(self, zone_id):
        """Verifica si una zona tiene incendio activo"""
        return zone_id in self.active_fires
    
    def get_fire_state(self, zone_id):
        """Obtiene el estado del incendio en una zona"""
        return self.active_fires.get(zone_id, None)

# ============================================
# GENERADOR DE LECTURAS
# ============================================
class SensorReading:
    """Genera lectura individual de sensor según el formato del documento"""
    
    @staticmethod
    def generate(zone_info, sensor_type, fire_state=None):
        """
        Genera lectura para un sensor específico
        
        Args:
            zone_info: dict con zone_id, lat, lon, region
            sensor_type: 'temperature', 'humidity', 'co2', 'wind_speed', 'wind_direction'
            fire_state: dict con offsets si hay incendio, None si no
        """
        
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        # Formato de sensor_id que coincide con la BD: S_Z_001_temp
        sensor_id = f"S_{zone_info['zone_id']}_{sensor_type[:4]}"
        
        # Obtener rangos según tipo
        ranges = getattr(SensorRanges, sensor_type.upper())
        
        # Generar valor base
        if fire_state is None:
            # Lectura normal
            value = random.uniform(*ranges['normal'])
        else:
            # Lectura anómala (incendio)
            if sensor_type == 'temperature':
                base = random.uniform(*ranges['normal'])
                value = base + fire_state['temp_offset']
                value = min(value, ranges['anomaly'][1])  # Cap máximo
                
            elif sensor_type == 'humidity':
                base = random.uniform(*ranges['normal'])
                value = base + fire_state['humidity_offset']
                value = min(value, ranges['anomaly'][0])  # Cap mínimo
                
            elif sensor_type == 'co2':
                base = random.uniform(*ranges['normal'])
                value = base + fire_state['co2_offset']
                value = min(value, ranges['anomaly'][1])
                
            elif sensor_type == 'wind_speed':
                base = random.uniform(*ranges['normal'])
                value = base + fire_state['wind_boost']
                value = min(value, ranges['anomaly'][1])
                
            elif sensor_type == 'wind_direction':
                # Dirección errática en incendios
                value = random.uniform(0, 360)
        
        # Formato JSON según documento
        return {
            'timestamp': timestamp,
            'sensor_id': sensor_id,
            'location': {
                'lat': zone_info['lat'],
                'lon': zone_info['lon'],
                'zone_id': zone_info['zone_id']
            },
            'sensor_type': sensor_type,
            'value': round(value, 2),
            'unit': ranges['unit']
        }

# ============================================
# SIMULADOR PRINCIPAL
# ============================================
class ForestFireSimulator:
    """Simulador completo de 100 sensores"""
    
    def __init__(self, num_zones=100):
        self.zones = ForestZones.generate_zones(num_zones)
        self.fire_manager = FireManager(num_zones)
        self.sensor_types = ['temperature', 'humidity', 'co2', 'wind_speed', 'wind_direction']
        
        # MQTT Publisher
        

        self.mqtt_client = mqtt.Client(
        client_id=f"detector_{np.random.randint(1000,9999)}"
    )
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_connected = False
        
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.mqtt_connected = True
            print(f"✅ Simulador conectado al broker MQTT")
        else:
            print(f"❌ Error de conexión MQTT: {rc}")
    
    def connect_mqtt(self):
        """Conecta al broker MQTT"""
        try:
            self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self.mqtt_client.loop_start()
            time.sleep(1)  # Esperar conexión
            return self.mqtt_connected
        except Exception as e:
            print(f"❌ Error conectando a MQTT: {e}")
            return False
    
    def publish_reading(self, reading):
        """Publica lectura individual al broker"""
        try:
            payload = json.dumps(reading)
            self.mqtt_client.publish(MQTT_TOPIC, payload, qos=1)
            return True
        except Exception as e:
            print(f"❌ Error publicando: {e}")
            return False
    
    def simulate_cycle(self):
        """Ejecuta un ciclo de simulación completo"""
        
        # Actualizar estado de incendios
        self.fire_manager.update_fires()
        
        # Estadísticas del ciclo
        readings_sent = 0
        fires_active = len(self.fire_manager.active_fires)
        
        # Generar lecturas para todas las zonas
        for zone in self.zones:
            zone_id = zone['zone_id']
            fire_state = self.fire_manager.get_fire_state(zone_id)
            
            # Generar lectura para cada tipo de sensor
            for sensor_type in self.sensor_types:
                reading = SensorReading.generate(zone, sensor_type, fire_state)
                
                if self.publish_reading(reading):
                    readings_sent += 1
        
        return readings_sent, fires_active
    
    def run(self, interval=30):
        """
        Ejecuta simulación continua
        
        Args:
            interval: segundos entre ciclos (30s según documento)
        """
        
        if not self.connect_mqtt():
            print("❌ No se pudo conectar al broker. Abortando.")
            return
        
        print("\n" + "="*70)
        print("🌲 SIMULADOR DE 100 SENSORES FORESTALES - INICIADO 🌲")
        print("="*70)
        print(f"📡 Publicando en topic: {MQTT_TOPIC}")
        print(f"🌍 Total zonas: {len(self.zones)}")
        print(f"⏱️  Intervalo: {interval} segundos")
        print(f"📊 Lecturas por ciclo: {len(self.zones) * len(self.sensor_types)}")
        print("="*70)
        print("\nPresiona Ctrl+C para detener\n")
        
        cycle_count = 0
        
        try:
            while True:
                cycle_count += 1
                start_time = time.time()
                
                readings_sent, fires_active = self.simulate_cycle()
                
                elapsed = time.time() - start_time
                
                # Mostrar resumen del ciclo
                timestamp = datetime.now().strftime("%H:%M:%S")
                fire_emoji = "🔥" if fires_active > 0 else "✅"
                
                print(f"{fire_emoji} [{timestamp}] Ciclo #{cycle_count} | "
                    f"Lecturas: {readings_sent} | "
                    f"Incendios activos: {fires_active} | "
                    f"Tiempo: {elapsed:.2f}s")
                
                if fires_active > 0:
                    fire_zones = list(self.fire_manager.active_fires.keys())
                    print(f"   🔥 Zonas con incendio: {', '.join(fire_zones[:5])}"
                        f"{' ...' if len(fire_zones) > 5 else ''}")
                
                # Esperar hasta completar intervalo
                sleep_time = max(0, interval - elapsed)
                time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Simulación detenida por el usuario")
            print(f"📊 Total ciclos ejecutados: {cycle_count}")
            print(f"📈 Total lecturas enviadas: {cycle_count * len(self.zones) * len(self.sensor_types)}")
        finally:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            print("👋 Desconectado del broker")

# ============================================
# PUNTO DE ENTRADA
# ============================================
if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║   SIMULADOR DE SENSORES IoT - 100 ZONAS FORESTALES           ║
    ║                                                                ║
    ║   📍 100 ubicaciones en 5 regiones de México                  ║
    ║   🌡️  5 sensores por ubicación (500 sensores totales)        ║
    ║   🔥 Simulación automática de incendios (2-5 simultáneos)    ║
    ║                                                                ║
    ║   Asegúrate de que Mosquitto esté corriendo:                 ║
    ║   $ mosquitto -v                                              ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    print("Presiona ENTER para iniciar la simulación...")
    
    simulator = ForestFireSimulator(num_zones=100)
    simulator.run(interval=30)  # 30 segundos según documento