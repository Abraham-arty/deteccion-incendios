# 🌲 Sistema de Detección de Incendios Forestales

Sistema IoT para detección temprana de incendios forestales usando sensores simulados, MQTT y Machine Learning (Isolation Forest).

Monitorea **100 zonas forestales** de México con **500 sensores** (temperatura, humedad, CO2, velocidad y dirección del viento).

---

## 🏗️ Arquitectura

```
deteccion-incendios/
├── supabase/          ← Versión cloud (Supabase + PostgreSQL remoto)
├── postgresql/        ← Versión local (PostgreSQL en tu máquina)
├── docker-compose.yml ← Infraestructura MQTT compartida
└── mosquitto.conf     ← Configuración del broker
```

Ambas versiones comparten la misma lógica de detección. La diferencia es el backend de base de datos.

---

## 🛠️ Tecnologías

- **Python 3.8+**
- **MQTT (Mosquitto)** — mensajería IoT entre sensores y detector
- **scikit-learn** — Isolation Forest para detección de anomalías
- **PostgreSQL + PostGIS** — almacenamiento con soporte geoespacial
- **Docker** — despliegue containerizado

---

## 🚀 Inicio rápido

### 1. Elige tu versión

| Versión | Cuándo usarla |
|---|---|
| `/supabase` | Base de datos en la nube, sin instalar PostgreSQL |
| `/postgresql` | Base de datos local, control total |

### 2. Configura las credenciales

```bash
# Entra a la carpeta de tu versión
cd supabase   # o cd postgresql

# Copia el archivo de ejemplo
cp .env.example .env

# Edita .env con tus credenciales
```

### 3. Instala dependencias

```bash
pip install -r requirements.txt
```

### 4. Levanta el broker MQTT

```bash
# Desde la raíz del proyecto
docker-compose up mosquitto -d
```

### 5. Ejecuta el sistema

```bash
# Terminal 1: detector
python anomaly_detector_supabase.py   # o anomaly_detector_db.py

# Terminal 2: simulador
python sensor_simulator.py
```

---

## 📊 Cómo funciona la detección

El sistema usa **Isolation Forest** por zona y tipo de sensor:

1. Acumula lecturas normales (primeras 10 por sensor)
2. Entrena un modelo por zona
3. Evalúa cada nueva lectura con un score (-1 anómalo → +1 normal)
4. Si 2+ sensores de la misma zona superan el umbral en menos de 10 minutos → **alerta de incendio**

La severidad se clasifica en **LEVE / MODERADO / SEVERO** según temperatura, humedad y CO2.

---

## 🗺️ Roadmap

| Fase | Descripción | Estado |
|---|---|---|
| 1 | Simulación de sensores + detección con Isolation Forest | ✅ Completada |
| 2 | Persistencia en PostgreSQL/Supabase + migración de datos | ✅ Completada |
| 3 | API REST + sistema de alertas en tiempo real | 🔄 En desarrollo |
| 4 | Dashboard de monitoreo geoespacial | 📋 Planeada |

---

## 📄 Licencia

Proyecto educativo — Ingeniería en Datos e Inteligencia Artificial
