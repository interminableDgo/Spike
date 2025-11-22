import requests
from locust import HttpUser, task, constant, LoadTestShape
from locust.exception import StopUser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# === 1. CONFIGURACIÓN ===
TARGET_IP = "104.248.215.179"
LOGIN_URL = f"http://{TARGET_IP}:5002/api/login"

CREDENTIALS = {
    "login": "carlos.gómez@heartguard.com",
    "password": "123"
}

TEST_DATA = {
    "patient_id": "7199cd3d-47ce-409f-89d5-9d01ca82fd08",
    "appointment_id": "db61d072-67ef-4cad-b396-6f86d13187df"
}

# === 2. DISEÑO DEL PICO (SPIKE) ===
class SpikeShape(LoadTestShape):
    """
    Controla los usuarios para crear un pico agresivo.
    """
    stages = [
        # 1. Base: 2 usuarios tranquilos (0s a 30s)
        {"duration": 30,  "users": 2, "spawn_rate": 1},
        
        # 2. EL PICO: ¡Subida agresiva! De 2 a 20 usuarios en 10 segundos (30s a 40s)
        # NOTA: 20 usuarios es el límite seguro para tu servidor Flask de desarrollo.
        # Si quieres probar el "crash", sube "users" a 100.
        {"duration": 40,  "users": 20, "spawn_rate": 4}, 
        
        # 3. Sostener el Pico: Aguantar la carga 20 segundos (40s a 60s)
        {"duration": 60,  "users": 20, "spawn_rate": 1},
        
        # 4. Recuperación: Bajar de golpe a la base (60s a 70s)
        {"duration": 70,  "users": 2, "spawn_rate": 10},
        
        # 5. Enfriamiento: Quedarse en base un poco y terminar (70s a 90s)
        {"duration": 90, "users": 2, "spawn_rate": 1},
        {"duration": 100, "users": 0,  "spawn_rate": 1}
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        return None

# === 3. EL SUPER USUARIO (OMNI DOCTOR) ===
class OmniDoctor(HttpUser):
    abstract = False
    # --- CORRECCIÓN: Definimos un host base por defecto para que Locust no falle ---
    host = f"http://{TARGET_IP}:5002" 
    
    # Tiempo de espera entre acciones (3 segundos para no saturar)
    wait_time = constant(3)
    token = None

    def on_start(self):
        # Configuración Anti-Bloqueo (Error 10054)
        self.client.keep_alive = False
        adapter = HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1))
        self.client.mount("http://", adapter)

        try:
            res = requests.post(LOGIN_URL, json=CREDENTIALS, headers={"Connection": "close"}, timeout=10)
            if res.status_code == 200:
                self.token = res.json().get("access_token")
            else:
                # Si falla el login en pleno pico, es esperado. Paramos el usuario.
                raise StopUser()
        except:
            raise StopUser()

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Connection": "close"
        }

    # --- TAREA MAESTRA ---
    @task(1)
    def flow_completo(self):
        try:
            # 1. Ver Cita (Puerto 5001)
            self.client.get(f"http://{TARGET_IP}:5001/api/appointments/{TEST_DATA['appointment_id']}", 
                           headers=self.get_headers(), name="1. Cita")
            
            # 2. Ver Vitales (Puerto 5006)
            self.client.get(f"http://{TARGET_IP}:5006/api/vitals", 
                           params={"patient_id": TEST_DATA['patient_id'], "range_hours": 24},
                           headers=self.get_headers(), name="2. Vitales")
        except:
            pass