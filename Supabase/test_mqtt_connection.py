"""
SCRIPT DE PRUEBA - CONEXIÓN MQTT
=================================
Verifica que Mosquitto esté corriendo y accesible.

USO:
    python test_mqtt_connection.py
"""

import paho.mqtt.client as mqtt
import time
import sys

def test_connection():
    """Prueba la conexión al broker MQTT"""
    
    print("🔍 Probando conexión a Mosquitto...\n")
    
    # Flags
    connected = False
    
    def on_connect(client, userdata, flags, rc):
        nonlocal connected
        if rc == 0:
            connected = True
            print("✅ ÉXITO: Conectado a Mosquitto")
            print(f"   Host: localhost")
            print(f"   Puerto: 1883")
        else:
            print(f"❌ ERROR: No se pudo conectar")
            print(f"   Código de error: {rc}")
            print("\n💡 Posibles soluciones:")
            print("   1. Inicia Mosquitto: sudo systemctl start mosquitto")
            print("   2. O con Docker: docker run -d -p 1883:1883 eclipse-mosquitto")
    
    # Crear cliente
    client = mqtt.Client(client_id="test_connection")
    # En produccion usaría:
    '''client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION1, 
    client_id=f"detector_{np.random.randint(1000,9999)}"
)'''
    client.on_connect = on_connect
    
    try:
        print("⏳ Intentando conectar...")
        client.connect("localhost", 1883, keepalive=5)
        client.loop_start()
        
        # Esperar conexión
        time.sleep(2)
        
        if connected:
            print("\n🎉 Sistema listo para usar!")
            print("\n📋 Siguiente paso:")
            print("   1. Abre una terminal: python anomaly_detector.py")
            print("   2. Abre otra terminal: python sensor_simulator.py")
            return True
        else:
            print("\n❌ No se pudo establecer conexión")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\n💡 ¿Mosquitto está instalado?")
        print("   Ubuntu/Debian: sudo apt-get install mosquitto")
        print("   macOS: brew install mosquitto")
        print("   Docker: docker run -d -p 1883:1883 eclipse-mosquitto")
        return False
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║          TEST DE CONEXIÓN MQTT                       ║
    ║   Verificando que Mosquitto esté accesible...       ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    
    success = test_connection()
    sys.exit(0 if success else 1)