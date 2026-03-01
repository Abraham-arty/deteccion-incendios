-- ============================================
-- SCHEMA PARA SISTEMA DE DETECCIÓN DE INCENDIOS
-- Base de datos: fire_detection
-- Versión: 1.0 - Fase 2
-- ============================================

-- Extensiones necesarias
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================
-- TABLA: sensors
-- Metadatos de sensores (500 sensores = 100 zonas x 5 tipos)
-- ============================================
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id VARCHAR(100) PRIMARY KEY,
    location GEOMETRY(Point, 4326) NOT NULL,
    zone_id VARCHAR(10) NOT NULL,
    region VARCHAR(50),
    sensor_type VARCHAR(100) NOT NULL,
    unit VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para búsquedas eficientes
CREATE INDEX IF NOT EXISTS idx_sensors_location ON sensors USING GIST(location);
CREATE INDEX IF NOT EXISTS idx_sensors_zone ON sensors(zone_id);
CREATE INDEX IF NOT EXISTS idx_sensors_type ON sensors(sensor_type);

-- Comentarios
COMMENT ON TABLE sensors IS 'Metadatos de todos los sensores del sistema';
COMMENT ON COLUMN sensors.sensor_id IS 'ID único del sensor (ej: S_Z_001_temp)';
COMMENT ON COLUMN sensors.location IS 'Ubicación geográfica (PostGIS Point)';
COMMENT ON COLUMN sensors.zone_id IS 'ID de la zona forestal (ej: Z_001)';
COMMENT ON COLUMN sensors.sensor_type IS 'Tipo: temperature, humidity, co2, wind_speed, wind_direction';

-- ============================================
-- TABLA: readings
-- Lecturas históricas de sensores (crece rápidamente)
-- ============================================
CREATE TABLE IF NOT EXISTS readings (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    sensor_id VARCHAR(100) REFERENCES sensors(sensor_id) ON DELETE CASCADE,
    value FLOAT NOT NULL,
    unit VARCHAR(10),
    is_anomaly BOOLEAN DEFAULT FALSE,
    anomaly_score FLOAT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para consultas rápidas
CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_readings_sensor ON readings(sensor_id);
CREATE INDEX IF NOT EXISTS idx_readings_anomaly ON readings(is_anomaly) WHERE is_anomaly = TRUE;
CREATE INDEX IF NOT EXISTS idx_readings_sensor_time ON readings(sensor_id, timestamp DESC);

-- Particionamiento por tiempo (opcional pero recomendado para producción)
-- CREATE TABLE readings_2024_11 PARTITION OF readings
--     FOR VALUES FROM ('2024-11-01') TO ('2024-12-01');

COMMENT ON TABLE readings IS 'Lecturas históricas de todos los sensores';
COMMENT ON COLUMN readings.is_anomaly IS 'TRUE si Isolation Forest detectó anomalía';
COMMENT ON COLUMN readings.anomaly_score IS 'Score del modelo (-1 anómalo, 1 normal)';

-- ============================================
-- TABLA: fire_incidents
-- Incendios detectados y confirmados
-- ============================================
CREATE TABLE IF NOT EXISTS fire_incidents (
    id SERIAL PRIMARY KEY,
    detected_at TIMESTAMP NOT NULL,
    location GEOMETRY(Point, 4326) NOT NULL,
    zone_id VARCHAR(10) NOT NULL,
    region VARCHAR(50),
    
    -- Estado del incendio
    confirmed_by_camera BOOLEAN DEFAULT FALSE,
    camera_confidence FLOAT,
    status VARCHAR(20) DEFAULT 'active', -- active, controlled, false_alarm
    
    -- Métricas del incendio
    affected_sensors_count INT,
    affected_sensor_types TEXT[], -- Array de tipos de sensores
    avg_anomaly_score FLOAT,
    
    -- Valores ambientales
    max_temperature FLOAT,
    min_humidity FLOAT,
    max_co2 FLOAT,
    wind_speed FLOAT,
    wind_direction FLOAT,
    
    -- Clasificación de severidad
    severity_score FLOAT,
    severity_class VARCHAR(20), -- LEVE, MODERADO, SEVERO
    
    -- Sistema de alertas
    alert_sent BOOLEAN DEFAULT FALSE,
    alert_sent_at TIMESTAMP,
    alert_recipients TEXT,
    
    -- Auditoría
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_incidents_detected ON fire_incidents(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_zone ON fire_incidents(zone_id);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON fire_incidents(severity_class);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON fire_incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_location ON fire_incidents USING GIST(location);

COMMENT ON TABLE fire_incidents IS 'Incendios detectados por el sistema';
COMMENT ON COLUMN fire_incidents.confirmed_by_camera IS 'TRUE si YOLO confirmó fuego/humo';
COMMENT ON COLUMN fire_incidents.severity_class IS 'Clasificación: LEVE, MODERADO, SEVERO';

-- ============================================
-- TABLA: fire_analysis
-- Análisis estadístico de cada incendio
-- ============================================
CREATE TABLE IF NOT EXISTS fire_analysis (
    id SERIAL PRIMARY KEY,
    incident_id INT REFERENCES fire_incidents(id) ON DELETE CASCADE,
    variable_name VARCHAR(50) NOT NULL,
    
    -- Valor anómalo vs normal
    anomaly_value FLOAT NOT NULL,
    normal_avg FLOAT NOT NULL,
    normal_std FLOAT NOT NULL,
    deviation_sigma FLOAT NOT NULL, -- desviaciones estándar
    
    -- Importancia de la variable
    importance_rank INT, -- 1 = más importante
    contribution_score FLOAT, -- contribución a severity_score
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_analysis_incident ON fire_analysis(incident_id);
CREATE INDEX IF NOT EXISTS idx_analysis_variable ON fire_analysis(variable_name);
CREATE INDEX IF NOT EXISTS idx_analysis_importance ON fire_analysis(importance_rank);

COMMENT ON TABLE fire_analysis IS 'Análisis estadístico detallado de variables en cada incendio';
COMMENT ON COLUMN fire_analysis.deviation_sigma IS 'Número de desviaciones estándar del valor normal';

-- ============================================
-- TABLA: system_stats
-- Estadísticas del sistema en tiempo real
-- ============================================
CREATE TABLE IF NOT EXISTS system_stats (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Contadores
    total_readings BIGINT,
    total_anomalies BIGINT,
    total_fires_detected INT,
    active_fires INT,
    
    -- Rendimiento
    readings_per_second FLOAT,
    avg_processing_time_ms FLOAT,
    
    -- Estado de modelos
    zones_monitored INT,
    zones_trained INT,
    
    -- Recursos
    cpu_usage_percent FLOAT,
    memory_usage_mb FLOAT
);

CREATE INDEX IF NOT EXISTS idx_stats_timestamp ON system_stats(timestamp DESC);

COMMENT ON TABLE system_stats IS 'Métricas del sistema para monitoreo y optimización';

-- ============================================
-- TABLA: alert_log
-- Log de todas las alertas enviadas
-- ============================================
CREATE TABLE IF NOT EXISTS alert_log (
    id SERIAL PRIMARY KEY,
    incident_id INT REFERENCES fire_incidents(id),
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    alert_type VARCHAR(20), -- webhook, email, sms
    recipient VARCHAR(255),
    status VARCHAR(20), -- sent, failed, pending
    response_code INT,
    response_body TEXT,
    retry_count INT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alert_incident ON alert_log(incident_id);
CREATE INDEX IF NOT EXISTS idx_alert_status ON alert_log(status);

COMMENT ON TABLE alert_log IS 'Registro de todas las alertas enviadas a servicios externos';

-- ============================================
-- VISTAS ÚTILES
-- ============================================

-- Vista: Sensores por zona
CREATE OR REPLACE VIEW sensors_by_zone AS
SELECT 
    zone_id,
    region,
    COUNT(*) as sensor_count,
    array_agg(DISTINCT sensor_type) as sensor_types,
    ST_AsGeoJSON(ST_Centroid(ST_Collect(location)))::json as zone_center
FROM sensors
GROUP BY zone_id, region;

COMMENT ON VIEW sensors_by_zone IS 'Resumen de sensores agrupados por zona';

-- Vista: Incendios activos con detalles
CREATE OR REPLACE VIEW active_fires AS
SELECT 
    fi.*,
    ST_AsGeoJSON(fi.location)::json as location_geojson,
    EXTRACT(EPOCH FROM (NOW() - fi.detected_at))/60 as minutes_active
FROM fire_incidents fi
WHERE fi.status = 'active'
ORDER BY fi.detected_at DESC;

COMMENT ON VIEW active_fires IS 'Incendios actualmente activos con información adicional';

-- Vista: Últimas lecturas por sensor
CREATE OR REPLACE VIEW latest_readings AS
SELECT DISTINCT ON (sensor_id)
    r.*,
    s.zone_id,
    s.sensor_type,
    s.region
FROM readings r
JOIN sensors s ON r.sensor_id = s.sensor_id
ORDER BY sensor_id, timestamp DESC;

COMMENT ON VIEW latest_readings IS 'Última lectura de cada sensor';

-- ============================================
-- FUNCIONES ÚTILES
-- ============================================

-- Función: Obtener incendios cercanos a una ubicación
CREATE OR REPLACE FUNCTION nearby_fires(
    lat FLOAT,
    lon FLOAT,
    radius_km FLOAT DEFAULT 10
)
RETURNS TABLE (
    incident_id INT,
    zone_id VARCHAR(10),
    severity_class VARCHAR(20),
    distance_km FLOAT,
    detected_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        fi.id,
        fi.zone_id,
        fi.severity_class,
        ST_Distance(
            fi.location::geography,
            ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography
        ) / 1000 as distance_km,
        fi.detected_at
    FROM fire_incidents fi
    WHERE fi.status = 'active'
    AND ST_DWithin(
        fi.location::geography,
        ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
        radius_km * 1000
    )
    ORDER BY distance_km;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION nearby_fires IS 'Encuentra incendios activos dentro de un radio';

-- Función: Actualizar timestamp de updated_at automáticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para fire_incidents
CREATE TRIGGER update_fire_incidents_updated_at
    BEFORE UPDATE ON fire_incidents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- DATOS INICIALES (OPCIONAL)
-- ============================================

-- Insertar sensores (se hará desde Python, pero aquí hay un ejemplo)
-- INSERT INTO sensors (sensor_id, location, zone_id, region, sensor_type, unit)
-- VALUES 
--     ('S_Z_001_temp', ST_SetSRID(ST_MakePoint(-104.5, 24.3), 4326), 'Z_001', 'Durango', 'temperature', 'celsius'),
--     ('S_Z_001_hum', ST_SetSRID(ST_MakePoint(-104.5, 24.3), 4326), 'Z_001', 'Durango', 'humidity', 'percent');

-- ============================================
-- PERMISOS (ajustar según necesidad)
-- ============================================

-- Usuario de aplicación
-- CREATE USER fireapp WITH PASSWORD 'secure_password';
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO fireapp;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO fireapp;

-- ============================================
-- MANTENIMIENTO
-- ============================================

-- Limpiar lecturas antiguas (ejecutar periódicamente)
-- DELETE FROM readings WHERE timestamp < NOW() - INTERVAL '30 days';

-- Vacuum para optimizar rendimiento
-- VACUUM ANALYZE;

-- ============================================
-- FIN DEL SCHEMA
-- ============================================

-- Verificar tablas creadas
SELECT table_name, table_type 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;