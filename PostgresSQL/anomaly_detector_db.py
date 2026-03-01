"""
DETECTOR DE ANOMALÍAS CON POSTGRESQL - VERSIÓN CORREGIDA
=========================================================
"""

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

import json
import numpy as np
from datetime import datetime, timedelta
from collections import deque, defaultdict
import paho.mqtt.client as mqtt
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import psycopg2
from psycopg2.extras import execute_batch
import threading
import time
import os

# ============================================
# CONFIGURACIÓN
# ============================================
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "sensores/forestales")

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME', 'fire_detection'),
}

# Modelo ML - REDUCIDO para entrenar más rápido
VENTANA_ENTRENAMIENTO = int(os.getenv('VENTANA_ENTRENAMIENTO', 10))
UMBRAL_ANOMALIA = float(os.getenv('UMBRAL_ANOMALIA', -0.3))
CONTAMINATION = 0.1        # 10% anomalías esperadas

# Detección de incendios
MIN_SENSORS_FOR_FIRE = int(os.getenv('MIN_SENSORS_FOR_FIRE', 2))
TIME_WINDOW_MINUTES = 10

# Batch insert
BATCH_SIZE = int(os.getenv('BATCH_SIZE', 100))
BATCH_INTERVAL = int(os.getenv('BATCH_INTERVAL', 5))

# ============================================
# DATABASE MANAGER (sin cambios)
# ============================================
class DatabaseManager:
    def __init__(self, config):
        self.config = config
        self.conn = None
        self.readings_buffer = []
        self.lock = threading.Lock()
        
    def connect(self):
        try:
            self.conn = psycopg2.connect(**self.config)
            self.conn.autocommit = False
            print("✅ Conectado a PostgreSQL")
            return True
        except psycopg2.Error as e:
            print(f"❌ Error conectando a PostgreSQL: {e}")
            return False
    
    def disconnect(self):
        if self.conn:
            self.conn.close()
            print("👋 Desconectado de PostgreSQL")
    
    def insert_reading(self, reading_data):
        with self.lock:
            self.readings_buffer.append(reading_data)
    
    def flush_readings(self):
        with self.lock:
            if not self.readings_buffer:
                return 0
            buffer_copy = self.readings_buffer.copy()
            self.readings_buffer.clear()
        
        try:
            cursor = self.conn.cursor()
            insert_query = """
                INSERT INTO readings (timestamp, sensor_id, value, unit, is_anomaly, anomaly_score)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            data = [
                (
                    r['timestamp'],
                    r['sensor_id'],
                    float(r['value']),
                    r['unit'],
                    bool(r.get('is_anomaly', False)),
                    float(r.get('anomaly_score')) if r.get('anomaly_score') is not None else None
                )
                for r in buffer_copy
            ]
            execute_batch(cursor, insert_query, data, page_size=BATCH_SIZE)
            self.conn.commit()
            cursor.close()
            return len(data)
        except psycopg2.Error as e:
            print(f"❌ Error insertando lecturas: {e}")
            self.conn.rollback()
            return 0
    
    def insert_fire_incident(self, fire_data):
        try:
            cursor = self.conn.cursor()
            
            avg_score = float(fire_data.get('avg_anomaly_score', 0) or 0)
            max_temp = float(fire_data['max_temperature']) if fire_data.get('max_temperature') is not None else None
            min_hum = float(fire_data['min_humidity']) if fire_data.get('min_humidity') is not None else None
            max_co2 = float(fire_data['max_co2']) if fire_data.get('max_co2') is not None else None
            wind_spd = float(fire_data['wind_speed']) if fire_data.get('wind_speed') is not None else None
            sev_score = float(fire_data.get('severity_score', 0) or 0)
            
            cursor.execute("""
                INSERT INTO fire_incidents (
                    detected_at, location, zone_id, region,
                    affected_sensors_count, affected_sensor_types,
                    avg_anomaly_score, max_temperature, min_humidity,
                    max_co2, wind_speed, severity_score, severity_class
                ) VALUES (
                    %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
                fire_data['detected_at'],
                float(fire_data.get('lon', -104.0)),
                float(fire_data.get('lat', 24.0)),
                str(fire_data['zone_id']),
                str(fire_data.get('region', 'Desconocida')),
                int(fire_data.get('affected_sensors_count', 0)),
                list(fire_data.get('affected_sensor_types', [])),
                avg_score,
                max_temp,
                min_hum,
                max_co2,
                wind_spd,
                sev_score,
                str(fire_data.get('severity_class', 'LEVE'))
            ))
            incident_id = cursor.fetchone()[0]
            self.conn.commit()
            cursor.close()
            return incident_id
        except psycopg2.Error as e:
            print(f"❌ Error insertando incendio: {e}")
            self.conn.rollback()
            return None
        
    def insert_fire_analysis(self, incident_id, analysis_data):
        try:
            cursor = self.conn.cursor()
            for i, analysis in enumerate(analysis_data):
                cursor.execute("""
                    INSERT INTO fire_analysis (
                        incident_id, variable_name, anomaly_value,
                        normal_avg, normal_std, deviation_sigma, importance_rank
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    int(incident_id),
                    str(analysis['variable']),
                    float(analysis['anomaly_value']),
                    float(analysis['normal_avg']),
                    float(analysis['normal_std']),
                    float(analysis['deviation_sigma']),
                    int(i + 1)
                ))
            self.conn.commit()
            cursor.close()
        except psycopg2.Error as e:
            print(f"❌ Error insertando análisis: {e}")
            self.conn.rollback()
            
    def get_statistics(self):
        try:
            cursor = self.conn.cursor()
            stats = {}
            cursor.execute("SELECT COUNT(*) FROM readings")
            stats['total_readings_db'] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM readings WHERE is_anomaly = TRUE")
            stats['total_anomalies_db'] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM fire_incidents")
            stats['total_fires_db'] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM fire_incidents WHERE status = 'active'")
            stats['active_fires_db'] = cursor.fetchone()[0]
            cursor.close()
            return stats
        except:
            return {}
    def get_zone_location(self, zone_id):
        """Obtiene ubicación de una zona desde la BD"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT region, 
                    ST_X(location::geometry) as lon, 
                    ST_Y(location::geometry) as lat
                FROM sensors 
                WHERE zone_id = %s 
                LIMIT 1
            """, (zone_id,))
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                return {
                    'region': result[0],
                    'lon': float(result[1]),
                    'lat': float(result[2])
                }
            
            # Valores por defecto si no se encuentra
            return {
                'region': 'Desconocida',
                'lon': -104.0,
                'lat': 24.0
            }
        except psycopg2.Error as e:
            print(f"⚠️ Error obteniendo ubicación: {e}")
            return {
                'region': 'Desconocida',
                'lon': -104.0,
                'lat': 24.0
            }
# ============================================
# DETECTOR POR ZONA - CORREGIDO
# ============================================
class ZoneDetector:
    def __init__(self, zone_id):
        self.zone_id = zone_id
        self.buffer = defaultdict(list)  # Cambiado a lista simple
        self.models = {}
        self.scalers = {}
        self.normal_stats = {}
        self.trained = False
        self.recent_anomalies = []
        
    def add_reading(self, sensor_type, value, timestamp):
        self.buffer[sensor_type].append({'value': value, 'timestamp': timestamp})
        # Mantener solo últimas 100 lecturas por tipo
        if len(self.buffer[sensor_type]) > 100:
            self.buffer[sensor_type] = self.buffer[sensor_type][-100:]
    
    def can_train(self):
        """Verifica si hay suficientes datos para entrenar"""
        if self.trained:
            return False
        if not self.buffer:
            return False
        # Necesitamos al menos VENTANA_ENTRENAMIENTO lecturas en al menos 2 tipos
        ready_count = sum(1 for readings in self.buffer.values() 
                        if len(readings) >= VENTANA_ENTRENAMIENTO)
        return ready_count >= 2
    
    def train_models(self):
        if self.trained:
            return False
        
        if not self.can_train():
            return False
        
        trained_count = 0
        
        for sensor_type, readings in self.buffer.items():
            if len(readings) < VENTANA_ENTRENAMIENTO:
                continue
            
            try:
                values = [r['value'] for r in readings]
                X = np.array(values).reshape(-1, 1)
                
                # Estadísticas normales
                self.normal_stats[sensor_type] = {
                    'mean': np.mean(values),
                    'std': max(np.std(values), 0.1)  # Evitar div by zero
                }
                
                # Normalizar
                scaler = StandardScaler()
                X_scaled = scaler.fit_transform(X)
                
                # Entrenar modelo
                model = IsolationForest(
                    contamination=CONTAMINATION,
                    n_estimators=50,  # Menos árboles = más rápido
                    random_state=42,
                    n_jobs=1
                )
                model.fit(X_scaled)
                
                self.models[sensor_type] = model
                self.scalers[sensor_type] = scaler
                trained_count += 1
                
            except Exception as e:
                print(f"⚠️ Error entrenando {sensor_type} en {self.zone_id}: {e}")
        
        if trained_count >= 2:
            self.trained = True
            return True
        return False
    
    def detect_anomaly(self, sensor_type, value, timestamp):
        if not self.trained:
            return {'is_anomaly': False, 'score': 0, 'trained': False}
        
        if sensor_type not in self.models:
            return {'is_anomaly': False, 'score': 0, 'trained': True}
        
        try:
            X = np.array([[value]])
            X_scaled = self.scalers[sensor_type].transform(X)
            
            prediction = self.models[sensor_type].predict(X_scaled)[0]
            score = self.models[sensor_type].score_samples(X_scaled)[0]
            
            is_anomaly = prediction == -1 or score < UMBRAL_ANOMALIA
            
            if is_anomaly:
                self.recent_anomalies.append({
                    'sensor_type': sensor_type,
                    'value': value,
                    'score': score,
                    'timestamp': timestamp
                })
                # Mantener solo últimas 20 anomalías
                if len(self.recent_anomalies) > 20:
                    self.recent_anomalies = self.recent_anomalies[-20:]
            
            return {'is_anomaly': is_anomaly, 'score': score, 'trained': True}
            
        except Exception as e:
            return {'is_anomaly': False, 'score': 0, 'trained': True}
    
    def check_fire_conditions(self):
        if len(self.recent_anomalies) < MIN_SENSORS_FOR_FIRE:
            return None
        
        now = datetime.utcnow()
        
        # Filtrar anomalías recientes
        recent = []
        for a in self.recent_anomalies:
            try:
                ts = datetime.fromisoformat(a['timestamp'].replace('Z', ''))
                if (now - ts).total_seconds() < TIME_WINDOW_MINUTES * 60:
                    recent.append(a)
            except:
                pass
        
        if len(recent) < MIN_SENSORS_FOR_FIRE:
            return None
        
        # Calcular métricas
        values_by_type = defaultdict(list)
        scores = []
        for a in recent:
            values_by_type[a['sensor_type']].append(a['value'])
            scores.append(abs(a['score']))
        
        avg_score = np.mean(scores) if scores else 0
        
        temp_vals = values_by_type.get('temperature', [])
        hum_vals = values_by_type.get('humidity', [])
        co2_vals = values_by_type.get('co2', [])
        wind_vals = values_by_type.get('wind_speed', [])
        
        severity_score, severity_class = self._calculate_severity(
            temp_vals, hum_vals, co2_vals, avg_score
        )
        
        analysis = self._calculate_analysis(values_by_type)
        
        # Limpiar anomalías después de detectar incendio
        self.recent_anomalies = []
        
        return {
            'zone_id': self.zone_id,
            'detected_at': now.isoformat() + 'Z',
            'affected_sensors_count': len(recent),
            'affected_sensor_types': list(set(a['sensor_type'] for a in recent)),
            'avg_anomaly_score': round(avg_score, 3),
            'max_temperature': max(temp_vals) if temp_vals else None,
            'min_humidity': min(hum_vals) if hum_vals else None,
            'max_co2': max(co2_vals) if co2_vals else None,
            'wind_speed': np.mean(wind_vals) if wind_vals else None,
            'severity_score': severity_score,
            'severity_class': severity_class,
            'analysis': analysis
        }
    
    def _calculate_severity(self, temp_vals, hum_vals, co2_vals, avg_score):
        score = 0
        if temp_vals and max(temp_vals) > 40: score += 3
        elif temp_vals and max(temp_vals) > 35: score += 2
        if hum_vals and min(hum_vals) < 25: score += 3
        elif hum_vals and min(hum_vals) < 35: score += 2
        if co2_vals and max(co2_vals) > 1000: score += 3
        elif co2_vals and max(co2_vals) > 700: score += 2
        if avg_score > 0.6: score += 2
        
        if score >= 7: return score, 'SEVERO'
        elif score >= 4: return score, 'MODERADO'
        else: return score, 'LEVE'
    
    def _calculate_analysis(self, values_by_type):
        analysis = []
        for sensor_type, values in values_by_type.items():
            if sensor_type in self.normal_stats and values:
                stats = self.normal_stats[sensor_type]
                anomaly_value = np.mean(values)
                deviation = abs(anomaly_value - stats['mean']) / stats['std']
                analysis.append({
                    'variable': sensor_type,
                    'anomaly_value': round(anomaly_value, 2),
                    'normal_avg': round(stats['mean'], 2),
                    'normal_std': round(stats['std'], 2),
                    'deviation_sigma': round(deviation, 2)
                })
        analysis.sort(key=lambda x: x['deviation_sigma'], reverse=True)
        return analysis

# ============================================
# DETECTOR GLOBAL - CORREGIDO
# ============================================
class GlobalFireDetectorDB:
    def __init__(self, db_manager):
        self.db = db_manager
        self.zone_detectors = {}
        self.active_fires = set()  # Solo IDs de zonas
        self.detected_fires = {}   # Detalles de incendios
        
        self.total_readings = 0
        self.total_anomalies = 0
        self.total_fires = 0
        self.zones_trained = 0
        
        self.flush_thread = None
        self.running = False
        
    def start_flush_thread(self):
        self.running = True
        self.flush_thread = threading.Thread(target=self._periodic_flush, daemon=True)
        self.flush_thread.start()
    
    def stop_flush_thread(self):
        self.running = False
        if self.flush_thread:
            self.flush_thread.join(timeout=2)
        self.db.flush_readings()
    
    def _periodic_flush(self):
        while self.running:
            time.sleep(BATCH_INTERVAL)
            self.db.flush_readings()
    
    def process_reading(self, reading):
        self.total_readings += 1
        
        zone_id = reading['location']['zone_id']
        sensor_type = reading['sensor_type']
        value = reading['value']
        timestamp = reading['timestamp']
        sensor_id = reading['sensor_id']
        unit = reading.get('unit', '')
        
        # Crear detector si no existe
        if zone_id not in self.zone_detectors:
            self.zone_detectors[zone_id] = ZoneDetector(zone_id)
        
        detector = self.zone_detectors[zone_id]
        detector.add_reading(sensor_type, value, timestamp)
        
        reading_data = {
            'timestamp': timestamp,
            'sensor_id': sensor_id,
            'value': value,
            'unit': unit,
            'is_anomaly': False,
            'anomaly_score': None
        }
        
        # Intentar entrenar si no está entrenado
        if not detector.trained:
            if detector.train_models():
                self.zones_trained += 1
                print(f"🎓 Modelo entrenado para {zone_id} ({self.zones_trained}/100)")
                self.db.insert_reading(reading_data)
                return {'status': 'trained', 'zone_id': zone_id}
            else:
                self.db.insert_reading(reading_data)
                return {'status': 'accumulating', 'zone_id': zone_id}
        
        # Detectar anomalía
        result = detector.detect_anomaly(sensor_type, value, timestamp)
        
        reading_data['is_anomaly'] = result['is_anomaly']
        reading_data['anomaly_score'] = result['score']
        self.db.insert_reading(reading_data)
        
        if result['is_anomaly']:
            self.total_anomalies += 1
            
            # Verificar incendio
            fire_info = detector.check_fire_conditions()
            
            if fire_info and zone_id not in self.active_fires:
                self.total_fires += 1
                self.active_fires.add(zone_id)
                
                # Ubicación
                location = self.db.get_zone_location(zone_id)
                if location:
                    fire_info.update(location)
                
                # Guardar en BD
                incident_id = self.db.insert_fire_incident(fire_info)
                if incident_id and fire_info.get('analysis'):
                    self.db.insert_fire_analysis(incident_id, fire_info['analysis'])
                
                fire_info['incident_id'] = incident_id
                self.detected_fires[zone_id] = fire_info
                
                return {'status': 'FIRE_DETECTED', 'fire_info': fire_info}
        
        return {'status': 'normal'}
    
    def get_statistics(self):
        stats = {
            'total_readings_memory': self.total_readings,
            'total_anomalies_memory': self.total_anomalies,
            'total_fires_memory': self.total_fires,
            'active_fires': len(self.active_fires),
            'zones_monitored': len(self.zone_detectors),
            'zones_trained': self.zones_trained,
            'buffer_size': len(self.db.readings_buffer)
        }
        db_stats = self.db.get_statistics()
        stats.update(db_stats)
        return stats

# ============================================
# CLIENTE MQTT
# ============================================
class MQTTFireDetectorDB:
    def __init__(self):
        self.db = DatabaseManager(DB_CONFIG)
        self.detector = None
        self.client = None
        self.last_stats_time = datetime.now()
        
    def setup(self):
        if not self.db.connect():
            return False
        
        self.detector = GlobalFireDetectorDB(self.db)
        self.detector.start_flush_thread()
        
        self.client = mqtt.Client(client_id=f"detector_db_{np.random.randint(1000,9999)}")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            return True
        except Exception as e:
            print(f"❌ Error MQTT: {e}")
            return False
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("✅ Conectado a MQTT")
            print(f"📡 Suscrito a: {MQTT_TOPIC}\n")
            self.client.subscribe(MQTT_TOPIC, qos=1)
    
    def on_message(self, client, userdata, msg):
        try:
            reading = json.loads(msg.payload.decode())
            result = self.detector.process_reading(reading)
            
            if result['status'] == 'FIRE_DETECTED':
                self._display_fire(result['fire_info'])
            
            if (datetime.now() - self.last_stats_time).seconds >= 30:
                self._display_stats()
                self.last_stats_time = datetime.now()
                
        except Exception as e:
            pass  # Silenciar errores para no saturar consola
    
    def _display_fire(self, fire):
        print(f"\n{'🔥'*30}")
        print(f"🚨 INCENDIO DETECTADO - {fire['zone_id']}")
        print(f"{'🔥'*30}")
        print(f"⏰ {fire['detected_at']}")
        print(f"📍 Región: {fire.get('region', 'N/A')}")
        print(f"📊 Severidad: {fire['severity_class']} (score: {fire['severity_score']})")
        print(f"🔍 Sensores: {', '.join(fire['affected_sensor_types'])}")
        print(f"💾 ID BD: {fire.get('incident_id', 'N/A')}")
        if fire.get('analysis'):
            print(f"📈 Variables críticas:")
            for a in fire['analysis'][:3]:
                print(f"   • {a['variable']}: {a['anomaly_value']} ({a['deviation_sigma']}σ)")
        print(f"{'🔥'*30}\n")
    
    def _display_stats(self):
        stats = self.detector.get_statistics()
        print(f"\n{'='*55}")
        print(f"📊 ESTADÍSTICAS")
        print(f"{'='*55}")
        print(f"🔄 Memoria: {stats['total_readings_memory']} lecturas, "
              f"{stats['total_anomalies_memory']} anomalías")
        print(f"💾 PostgreSQL: {stats.get('total_readings_db', 0)} lecturas, "
              f"{stats.get('total_fires_db', 0)} incendios")
        print(f"🌲 Zonas: {stats['zones_monitored']} monitoreadas, "
              f"{stats['zones_trained']} entrenadas")
        print(f"🔥 Incendios activos: {stats['active_fires']}")
        print(f"{'='*55}\n")
    
    def run(self):
        try:
            self.client.loop_forever()
        except KeyboardInterrupt:
            print("\n🛑 Deteniendo...")
        finally:
            self.detector.stop_flush_thread()
            self._display_stats()
            self.db.disconnect()
            self.client.disconnect()

# ============================================
# MAIN
# ============================================
def main():
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║   DETECTOR DE INCENDIOS CON POSTGRESQL - v2.0        ║
    ║                                                       ║
    ║   🌲 Isolation Forest (entrena rápido)               ║
    ║   💾 Guarda en PostgreSQL                            ║
    ║   🔥 Detecta incendios en tiempo real                ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    
    detector = MQTTFireDetectorDB()
    
    if not detector.setup():
        print("❌ Error configurando detector")
        return
    
    print("🚀 Esperando datos del simulador...\n")
    detector.run()

if __name__ == "__main__":
    main()