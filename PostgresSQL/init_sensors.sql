DO $$
DECLARE
    regions TEXT[][] := ARRAY[
        ARRAY['Chihuahua', '27.0', '29.0', '-108.0', '-106.0'],
        ARRAY['Durango', '24.0', '25.5', '-105.5', '-104.0'],
        ARRAY['Jalisco', '19.5', '21.0', '-104.5', '-103.0'],
        ARRAY['Michoacán', '18.5', '20.0', '-103.5', '-101.0'],
        ARRAY['Oaxaca', '15.5', '18.0', '-98.0', '-95.0']
    ];
    region_idx INT;
    region_name TEXT;
    lat_min FLOAT;
    lat_max FLOAT;
    lon_min FLOAT;
    lon_max FLOAT;
    zone_id_str TEXT;
    lat FLOAT;
    lon FLOAT;
    sensor_types TEXT[] := ARRAY['temperature', 'humidity', 'co2', 'wind_speed', 'wind_direction'];
    sensor_type TEXT;
    sensor_suffix TEXT;
    unit_type VARCHAR(10);
    current_sensor_type TEXT;  -- Variable diferente para el loop
    current_region TEXT;        -- Variable diferente para el loop
    sensor_count INT;
BEGIN
    RAISE NOTICE '🚀 Insertando 500 sensores en 100 zonas forestales...';
    RAISE NOTICE '   5 sensores por zona: temperature, humidity, co2, wind_speed, wind_direction';
    RAISE NOTICE '';
    
    FOR i IN 1..100 LOOP
        region_idx := ((i-1) % 5) + 1;
        region_name := regions[region_idx][1];
        lat_min := regions[region_idx][2]::FLOAT;
        lat_max := regions[region_idx][3]::FLOAT;
        lon_min := regions[region_idx][4]::FLOAT;
        lon_max := regions[region_idx][5]::FLOAT;
        zone_id_str := 'Z_' || LPAD(i::TEXT, 3, '0');
        lat := lat_min + (lat_max - lat_min) * random();
        lon := lon_min + (lon_max - lon_min) * random();
        
        FOREACH sensor_type IN ARRAY sensor_types LOOP
            sensor_suffix := CASE 
                WHEN sensor_type = 'temperature' THEN 'temp'
                WHEN sensor_type = 'humidity' THEN 'humi'
                WHEN sensor_type = 'co2' THEN 'co2'
                WHEN sensor_type = 'wind_speed' THEN 'wind'
                WHEN sensor_type = 'wind_direction' THEN 'wind_dir'
            END;
            
            unit_type := CASE 
                WHEN sensor_type = 'temperature' THEN 'celsius'
                WHEN sensor_type = 'humidity' THEN 'percent'
                WHEN sensor_type = 'co2' THEN 'ppm'
                WHEN sensor_type = 'wind_speed' THEN 'km/h'
                WHEN sensor_type = 'wind_direction' THEN 'degrees'
            END;
            
            INSERT INTO sensors (
                sensor_id,
                location,
                zone_id,
                region,
                sensor_type,
                unit
            ) VALUES (
                'S_' || zone_id_str || '_' || sensor_suffix,
                ST_SetSRID(ST_MakePoint(lon, lat), 4326),
                zone_id_str,
                region_name,
                sensor_type,
                unit_type
            );
        END LOOP;
        
        IF i % 25 = 0 THEN
            RAISE NOTICE '⏳ Progreso: %/100 zonas procesadas', i;
        END IF;
    END LOOP;
    
    RAISE NOTICE '';
    RAISE NOTICE '✅ INSERCIÓN COMPLETADA';
    RAISE NOTICE '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━';
    RAISE NOTICE '📊 Total sensores: %', (SELECT COUNT(*) FROM sensors);
    RAISE NOTICE '📍 Total zonas: %', (SELECT COUNT(DISTINCT zone_id) FROM sensors);
    RAISE NOTICE '';
    
    RAISE NOTICE '🌡️  Distribución por tipo de sensor:';
    FOR current_sensor_type IN 
        SELECT DISTINCT s.sensor_type 
        FROM sensors s 
        ORDER BY s.sensor_type 
    LOOP
        SELECT COUNT(*) INTO sensor_count 
        FROM sensors 
        WHERE sensors.sensor_type = current_sensor_type;
        
        RAISE NOTICE '   • %: % sensores', 
            RPAD(current_sensor_type, 20, ' '),
            sensor_count;
    END LOOP;
    
    RAISE NOTICE '';
    RAISE NOTICE '🗺️  Distribución por región:';
    FOR current_region IN 
        SELECT DISTINCT region 
        FROM sensors 
        ORDER BY region 
    LOOP
        SELECT COUNT(*) INTO sensor_count 
        FROM sensors 
        WHERE sensors.region = current_region;
        
        RAISE NOTICE '   • %: % sensores', 
            RPAD(current_region, 20, ' '),
            sensor_count;
    END LOOP;
    
    RAISE NOTICE '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━';
    
END $$;