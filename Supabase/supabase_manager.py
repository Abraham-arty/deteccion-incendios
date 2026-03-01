from supabase import create_client, Client
import psycopg2
from psycopg2.extras import execute_batch

# Cargar variables de entorno
load_dotenv()

class SupabaseManager:
    """
    Manager para operaciones con Supabase.
    Usa tanto el cliente de Supabase como conexión directa PostgreSQL.
    """
    
    def __init__(self):
        # Credenciales Supabase
        self.url = os.getenv('SUPABASE_URL')
        self.key = os.getenv('SUPABASE_KEY')
        self.service_key = os.getenv('SUPABASE_SERVICE_KEY')
        
        # Credenciales PostgreSQL directo
        self.db_config = {
            'host': os.getenv('SUPABASE_DB_HOST'),
            'port': int(os.getenv('SUPABASE_DB_PORT', 5432)),
            'user': os.getenv('SUPABASE_DB_USER', 'postgres'),
            'password': os.getenv('SUPABASE_DB_PASSWORD'),
            'database': os.getenv('SUPABASE_DB_NAME', 'postgres'),
        }
        
        # Clientes
        self.supabase: Optional[Client] = None
        self.pg_conn = None
        
        # Buffer para inserciones batch
        self.readings_buffer = []
        self.lock = threading.Lock()
        
        # Validar configuración
        self._validate_config()
    
    def _validate_config(self):
        """Valida que todas las variables de entorno estén configuradas"""
        required_vars = ['SUPABASE_URL', 'SUPABASE_KEY', 'SUPABASE_DB_HOST', 'SUPABASE_DB_PASSWORD']
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            raise ValueError(
                f"❌ Faltan variables de entorno: {', '.join(missing)}\n"
                f"💡 Copia .env.example a .env y configura tus credenciales de Supabase"
            )
    
    def connect(self) -> bool:
        """Establece conexión con Supabase"""
        try:
            print("🔌 Conectando a Supabase...")
            
            # Cliente Supabase (para operaciones REST)
            self.supabase = create_client(self.url, self.key)
            
            # Conexión PostgreSQL directa (para batch inserts rápidos)
            self.pg_conn = psycopg2.connect(**self.db_config)
            self.pg_conn.autocommit = False
            
            # Verificar conexión
            cursor = self.pg_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sensors")
            sensor_count = cursor.fetchone()[0]
            cursor.close()
            
            print(f"✅ Conectado a Supabase")
            print(f"📊 Sensores en BD: {sensor_count}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error conectando a Supabase: {e}")
            return False
    
    def disconnect(self):
        """Cierra conexiones"""
        if self.pg_conn:
            self.pg_conn.close()
            print("👋 Desconectado de Supabase")
    
    # ============================================
    # OPERACIONES CON READINGS
    # ============================================
    
    def insert_reading(self, reading_data: Dict[str, Any]):
        """Agrega lectura al buffer para inserción batch"""
        with self.lock:
            self.readings_buffer.append(reading_data)
    
    def flush_readings(self) -> int:
        """Inserta todas las lecturas del buffer en batch"""
        with self.lock:
            if not self.readings_buffer:
                return 0
            buffer_copy = self.readings_buffer.copy()
            self.readings_buffer.clear()
        
        try:
            cursor = self.pg_conn.cursor()
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
            
            execute_batch(cursor, insert_query, data, page_size=100)
            self.pg_conn.commit()
            cursor.close()
            
            return len(data)
            
        except psycopg2.Error as e:
            print(f"❌ Error insertando lecturas: {e}")
            self.pg_conn.rollback()
            return 0
    
    # ============================================
    # OPERACIONES CON FIRE INCIDENTS
    # ============================================
    
    def insert_fire_incident(self, fire_data: Dict[str, Any]) -> Optional[int]:
        """Inserta un nuevo incendio detectado"""
        try:
            cursor = self.pg_conn.cursor()
            
            # Preparar valores
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
            self.pg_conn.commit()
            cursor.close()
            
            return incident_id
            
        except psycopg2.Error as e:
            print(f"❌ Error insertando incendio: {e}")
            self.pg_conn.rollback()
            return None
    
    def insert_fire_analysis(self, incident_id: int, analysis_data: List[Dict[str, Any]]):
        """Inserta análisis estadístico de un incendio"""
        try:
            cursor = self.pg_conn.cursor()
            
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
            
            self.pg_conn.commit()
            cursor.close()
            
        except psycopg2.Error as e:
            print(f"❌ Error insertando análisis: {e}")
            self.pg_conn.rollback()
    
    def update_fire_status(self, incident_id: int, status: str, 
                          confirmed_by_camera: bool = False,
                          camera_confidence: float = None):
        """
        Actualiza el estado de un incendio.
        Útil para Fase 3 cuando YOLO confirme el incendio.
        """
        try:
            cursor = self.pg_conn.cursor()
            
            cursor.execute("""
                UPDATE fire_incidents 
                SET status = %s,
                    confirmed_by_camera = %s,
                    camera_confidence = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (status, confirmed_by_camera, camera_confidence, incident_id))
            
            self.pg_conn.commit()
            cursor.close()
            
            return True
            
        except psycopg2.Error as e:
            print(f"❌ Error actualizando estado: {e}")
            self.pg_conn.rollback()
            return False
    
    # ============================================
    # CONSULTAS Y ESTADÍSTICAS
    # ============================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obtiene estadísticas del sistema"""
        try:
            cursor = self.pg_conn.cursor()
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
    
    def get_zone_location(self, zone_id: str) -> Dict[str, Any]:
        """Obtiene ubicación de una zona desde la BD"""
        try:
            cursor = self.pg_conn.cursor()
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
    
    def get_active_fires(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los incendios activos.
        Útil para la web y futuras fases.
        """
        try:
            response = self.supabase.table('fire_incidents')\
                .select('*')\
                .eq('status', 'active')\
                .order('detected_at', desc=True)\
                .execute()
            
            return response.data
            
        except Exception as e:
            print(f"❌ Error obteniendo incendios: {e}")
            return []
    
    def get_latest_readings(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Obtiene las últimas lecturas.
        Útil para dashboard en tiempo real.
        """
        try:
            response = self.supabase.table('readings')\
                .select('*, sensors(*)')\
                .order('timestamp', desc=True)\
                .limit(limit)\
                .execute()
            
            return response.data
            
        except Exception as e:
            print(f"❌ Error obteniendo lecturas: {e}")
            return []
    
    # ============================================
    # ALERTAS (Preparación para Fase 3)
    # ============================================
    
    def log_alert(self, incident_id: int, alert_type: str, 
                  recipient: str, status: str = 'sent',
                  response_code: int = None, response_body: str = None):
        """
        Registra una alerta enviada.
        Para Fase 3: webhooks, emails, SMS.
        """
        try:
            cursor = self.pg_conn.cursor()
            
            cursor.execute("""
                INSERT INTO alert_log (
                    incident_id, alert_type, recipient, 
                    status, response_code, response_body
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (incident_id, alert_type, recipient, status, response_code, response_body))
            
            self.pg_conn.commit()
            cursor.close()
            
        except psycopg2.Error as e:
            print(f"❌ Error registrando alerta: {e}")
            self.pg_conn.rollback()