#!/bin/bash

set -e

# Verificação de Root
if [ "$EUID" -eq 0 ]; then
  echo "❌ ERRO: Não execute este script como root/sudo."
  echo "Execute apenas: bash install_volant_fixed.sh"
  exit 1
fi

echo "=========================================================="
echo "   🎮 INSTALADOR VOLANT CONTROLLER - VERSÃO OTIMIZADA    "
echo "=========================================================="

DIR_NAME="VolantController"

# Limpeza
if [ -d "$DIR_NAME" ] || [ -d "$HOME/.buildozer" ]; then
    echo "🧹 [1/7] Limpando instalações anteriores..."
    sudo rm -rf "$DIR_NAME"
    sudo rm -rf ~/.buildozer
fi

# Dependências do Sistema
echo "📦 [2/7] Instalando dependências do sistema..."
sudo apt update
sudo apt install -y \
    git zip unzip openjdk-17-jdk python3-pip \
    autoconf libtool pkg-config zlib1g-dev \
    libncurses-dev cmake libffi-dev libssl-dev \
    python3-venv libzbar-dev build-essential \
    ccache libltdl-dev

# Criação do Diretório
echo "📁 [3/7] Criando estrutura do projeto..."
mkdir "$DIR_NAME"
cd "$DIR_NAME"

# Ambiente Virtual
echo "🐍 [4/7] Configurando Python Virtual Environment..."
python3 -m venv .venv
source .venv/bin/activate

# Instalação de Ferramentas Python
echo "🔧 [5/7] Instalando ferramentas Python..."
pip install --upgrade pip setuptools wheel
pip install Cython==0.29.33
pip install buildozer==1.5.0

# Geração do main.py
echo "📝 [6/7] Gerando main.py otimizado..."
cat > main.py << 'PYTHON_EOF'
import json
import threading
import time
import socket
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform
from kivy.properties import StringProperty

# Importações condicionais
accelerometer = None
websocket = None
Camera = None

try:
    from plyer import accelerometer
    import websocket
    
    if platform == 'android':
        from kivy.uix.camera import Camera
except ImportError as e:
    print(f"Import warning: {e}")

if platform != 'android':
    Window.size = (800, 400)

KV = """
#:import hex kivy.utils.get_color_from_hex

<GamepadButton@Button>:
    background_normal: ''
    background_down: ''
    background_color: hex('#333333') if self.state == 'normal' else hex('#00FFFF')
    color: hex('#E0E0E0') if self.state == 'normal' else hex('#121212')
    font_size: '20sp'
    bold: True

<ConnectionScreen>:
    canvas.before:
        Color:
            rgba: hex('#121212')
        Rectangle:
            pos: self.pos
            size: self.size
    
    BoxLayout:
        orientation: 'vertical'
        padding: 20
        spacing: 15
        
        Label:
            text: "Volant Controller"
            size_hint_y: 0.2
            font_size: '32sp'
            color: hex('#00FFFF')
            bold: True

        Button:
            text: "Buscar Servidores Automático"
            size_hint_y: 0.2
            background_color: hex('#00FFFF')
            color: hex('#121212')
            bold: True
            on_press: root.scan_network()
        
        Button:
            text: "Inserir IP Manual"
            size_hint_y: 0.15
            background_color: hex('#FFAA00')
            color: hex('#121212')
            on_press: root.show_ip_input()

        Button:
            text: "Conectar via USB (ADB)"
            size_hint_y: 0.15
            background_color: hex('#00FF00')
            color: hex('#121212')
            on_press: root.connect_usb()
        
        Label:
            id: status_label
            text: root.status_text
            size_hint_y: 0.15
            color: hex('#FFFFFF')
            font_size: '16sp'

<IPInputScreen>:
    canvas.before:
        Color:
            rgba: hex('#121212')
        Rectangle:
            pos: self.pos
            size: self.size
    BoxLayout:
        orientation: 'vertical'
        padding: 20
        spacing: 15
        Label:
            text: "Digite o IP do Servidor"
            size_hint_y: 0.2
            color: hex('#00FFFF')
            font_size: '24sp'
        TextInput:
            id: ip_input
            text: "192.168.1.100"
            multiline: False
            size_hint_y: 0.15
            font_size: '20sp'
            hint_text: "Ex: 192.168.1.100"
        BoxLayout:
            size_hint_y: 0.2
            spacing: 10
            Button:
                text: "Conectar"
                background_color: hex('#00FFFF')
                bold: True
                on_press: root.connect_ip()
            Button:
                text: "Voltar"
                background_color: hex('#FF3333')
                on_press: root.go_back()

<NetworkListScreen>:
    canvas.before:
        Color:
            rgba: hex('#121212')
        Rectangle:
            pos: self.pos
            size: self.size
    BoxLayout:
        orientation: 'vertical'
        padding: 20
        spacing: 10
        Label:
            text: root.title_text
            size_hint_y: 0.15
            font_size: '24sp'
            color: hex('#00FFFF')
            bold: True
        ScrollView:
            size_hint_y: 0.7
            GridLayout:
                id: device_list
                cols: 1
                spacing: 10
                size_hint_y: None
                height: self.minimum_height
        BoxLayout:
            size_hint_y: 0.15
            spacing: 10
            Button:
                text: "Atualizar"
                background_color: hex('#00FFFF')
                color: hex('#121212')
                bold: True
                on_press: root.refresh()
            Button:
                text: "Voltar"
                background_color: hex('#FF3333')
                on_press: root.go_back()

<MainLayout>:
    canvas.before:
        Color:
            rgba: hex('#121212')
        Rectangle:
            pos: self.pos
            size: self.size

    Label:
        text: root.connection_info
        pos_hint: {'x': 0.02, 'top': 0.98}
        size_hint: 0.6, 0.08
        color: hex('#00FF00')
        font_size: '16sp'
        bold: True

    Button:
        text: "DESCONECTAR"
        background_color: hex('#FF3333')
        color: hex('#FFFFFF')
        bold: True
        pos_hint: {'right': 0.70, 'top': 0.98}
        size_hint: 0.25, 0.08
        on_press: root.disconnect()

    GamepadButton:
        text: "LB"
        pos_hint: {'x': 0.05, 'center_y': 0.90}
        size_hint: 0.15, 0.30
        on_press: root.send_btn('BTN_TL', 1)
        on_release: root.send_btn('BTN_TL', 0)

    BoxLayout:
        orientation: 'vertical'
        pos_hint: {'x': 0.05, 'center_y': 0.62}
        size_hint: 0.15, 0.2
        Label:
            text: "LT"
            size_hint_y: 0.3
            color: hex('#FFAA00')
            font_size: '18sp'
            bold: True
        Slider:
            orientation: 'vertical'
            min: 0
            max: 255
            value: 0
            size_hint_y: 0.9
            on_value: root.send_trigger('ABS_Z', self.value)

    GamepadButton:
        text: "Y"
        pos_hint: {'x': 0.12, 'center_y': 0.38}
        size_hint: 0.10, 0.15
        on_press: root.send_btn('BTN_WEST', 1)
        on_release: root.send_btn('BTN_WEST', 0)

    GamepadButton:
        text: "X"
        pos_hint: {'x': 0.02, 'center_y': 0.28}
        size_hint: 0.10, 0.15
        on_press: root.send_btn('BTN_NORTH', 1)
        on_release: root.send_btn('BTN_NORTH', 0)

    ToggleButton:
        text: "Volante: ON" if self.state == 'down' else "Volante: OFF"
        state: 'down'
        background_normal: ''
        background_color: hex('#00FFFF') if self.state == 'down' else hex('#333333')
        color: hex('#121212') if self.state == 'down' else hex('#E0E0E0')
        pos_hint: {'center_x': 0.5, 'center_y': 0.4}
        size_hint: 0.22, 0.15
        bold: True
        on_state: root.toggle_tilt(self.state == 'down')

    GamepadButton:
        text: "SELECT"
        pos_hint: {'center_x': 0.4, 'y': 0.05}
        size_hint: 0.15, 0.1
        font_size: '16sp'
        on_press: root.send_btn('BTN_SELECT', 1)
        on_release: root.send_btn('BTN_SELECT', 0)

    GamepadButton:
        text: "START"
        pos_hint: {'center_x': 0.6, 'y': 0.05}
        size_hint: 0.15, 0.1
        font_size: '16sp'
        on_press: root.send_btn('BTN_START', 1)
        on_release: root.send_btn('BTN_START', 0)

    GamepadButton:
        text: "RB"
        pos_hint: {'right': 0.95, 'center_y': 0.90}
        size_hint: 0.15, 0.30
        on_press: root.send_btn('BTN_TR', 1)
        on_release: root.send_btn('BTN_TR', 0)

    BoxLayout:
        orientation: 'vertical'
        pos_hint: {'right': 0.95, 'center_y': 0.62}
        size_hint: 0.15, 0.2
        Label:
            text: "RT"
            size_hint_y: 0.3
            color: hex('#FFAA00')
            font_size: '18sp'
            bold: True
        Slider:
            orientation: 'vertical'
            min: 0
            max: 255
            value: 0
            size_hint_y: 0.9
            on_value: root.send_trigger('ABS_RZ', self.value)

    GamepadButton:
        text: "B"
        pos_hint: {'right': 0.88, 'center_y': 0.38}
        size_hint: 0.10, 0.15
        on_press: root.send_btn('BTN_B', 1)
        on_release: root.send_btn('BTN_B', 0)

    GamepadButton:
        text: "A"
        pos_hint: {'right': 0.98, 'center_y': 0.28}
        size_hint: 0.10, 0.15
        on_press: root.send_btn('BTN_A', 1)
        on_release: root.send_btn('BTN_A', 0)
"""

class ConnectionScreen(Screen):
    status_text = StringProperty("Pronto para conectar")
    
    def show_ip_input(self):
        self.manager.current = 'ip_input'

    def scan_network(self):
        self.status_text = "Procurando servidores na rede..."
        self.manager.get_screen('network_list').set_mode('scan')
        self.manager.current = 'network_list'

    def connect_usb(self):
        self.status_text = "Conectando via USB..."
        App.get_running_app().connect_websocket('127.0.0.1', 'usb')

class IPInputScreen(Screen):
    def connect_ip(self):
        ip = self.ids.ip_input.text.strip()
        if ip:
            App.get_running_app().connect_websocket(ip, 'manual')
    
    def go_back(self):
        self.manager.current = 'connection'

class NetworkListScreen(Screen):
    title_text = StringProperty("Dispositivos")
    mode = StringProperty('scan')
    is_scanning = False
    found_ips = []
    
    def set_mode(self, mode):
        self.mode = mode
        self.refresh()
    
    def refresh(self):
        self.ids.device_list.clear_widgets()
        self.found_ips = []
        self.title_text = "Procurando..."
        self.start_scan()
    
    def start_scan(self):
        self.stop_scan()
        self.is_scanning = True
        threading.Thread(target=self._udp_scan, daemon=True).start()
        threading.Thread(target=self._tcp_scan, daemon=True).start()
        
        btn = Button(
            text="Buscando servidores...\nAguarde até 20 segundos",
            size_hint_y=None,
            height=90,
            background_color=[0.2, 0.6, 0.8, 1],
            bold=True
        )
        self.ids.device_list.add_widget(btn)

    def _udp_scan(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(('', 5000))
            sock.settimeout(2)
            
            start = time.time()
            while time.time() - start < 20 and self.is_scanning:
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = json.loads(data.decode('utf-8'))
                    if msg.get('type') == 'volant_server':
                        self.add_server(
                            msg.get('name', 'Volant'),
                            msg.get('ip', addr[0]),
                            "UDP Broadcast"
                        )
                except socket.timeout:
                    pass
                except:
                    pass
            sock.close()
        except Exception as e:
            print(f"UDP scan error: {e}")

    def _tcp_scan(self):
        try:
            local_ip = self._get_ip()
            base = ".".join(local_ip.split('.')[:-1])
            
            for i in range(1, 255):
                if not self.is_scanning:
                    break
                ip = f"{base}.{i}"
                if ip != local_ip:
                    threading.Thread(
                        target=self._check_port,
                        args=(ip,),
                        daemon=True
                    ).start()
                time.sleep(0.03)
        except Exception as e:
            print(f"TCP scan error: {e}")

    def _check_port(self, ip):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.6)
        try:
            if sock.connect_ex((ip, 8080)) == 0:
                self.add_server("Volant Server", ip, "Port 8080")
        except:
            pass
        finally:
            sock.close()

    def _get_ip(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(('8.8.8.8', 80))
            return sock.getsockname()[0]
        except:
            return '192.168.1.1'
        finally:
            sock.close()

    def add_server(self, name, ip, method):
        if ip not in self.found_ips:
            self.found_ips.append(ip)
            Clock.schedule_once(lambda dt: self._add_button(name, ip, method))

    def _add_button(self, name, ip, method):
        if self.ids.device_list.children and "Buscando" in self.ids.device_list.children[-1].text:
            self.ids.device_list.clear_widgets()
        
        btn = Button(
            text=f"{name}\n {ip}\n{method}",
            size_hint_y=None,
            height=110,
            background_color=[0, 1, 1, 1],
            color=[0.1, 0.1, 0.1, 1],
            halign='center',
            bold=True
        )
        btn.bind(on_press=lambda x: self.connect(ip))
        self.ids.device_list.add_widget(btn)

    def stop_scan(self):
        self.is_scanning = False
    
    def connect(self, ip):
        self.stop_scan()
        App.get_running_app().connect_websocket(ip, 'auto')
    
    def go_back(self):
        self.stop_scan()
        self.manager.current = 'connection'

class MainLayout(FloatLayout):
    connection_info = StringProperty("Conectado")
    ws = None
    tilt_enabled = True
    last_tilt = 0
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if accelerometer:
            try:
                accelerometer.enable()
                Clock.schedule_interval(self.update_tilt, 1.0 / 30)
            except:
                pass

    def send_payload(self, data):
        if self.ws:
            try:
                self.ws.send(json.dumps(data))
            except:
                pass
    
    def send_btn(self, code, val):
        threading.Thread(
            target=self.send_payload,
            args=({"type": "key", "code": code, "value": val},),
            daemon=True
        ).start()

    def send_trigger(self, code, val):
        threading.Thread(
            target=self.send_payload,
            args=({"type": "abs", "code": code, "value": int(val)},),
            daemon=True
        ).start()

    def toggle_tilt(self, active):
        self.tilt_enabled = active
        if not active:
            self.send_tilt(0)

    def send_tilt(self, val):
        threading.Thread(
            target=self.send_payload,
            args=({"type": "abs", "code": "ABS_X", "value": int(val)},),
            daemon=True
        ).start()

    def update_tilt(self, dt):
        if not self.tilt_enabled or not accelerometer:
            return
        try:
            acc = accelerometer.acceleration
            if acc:
                y = acc[1]
                val = (max(min(y, 7.0), -7.0) / 7.0) * 255 * 1
                if abs(val - self.last_tilt) > 5:
                    self.send_tilt(val)
                    self.last_tilt = val
        except:
            pass

    def disconnect(self):
        App.get_running_app().disconnect_all()

class VolantApp(App):
    def build(self):
        Builder.load_string(KV)
        self.sm = ScreenManager()
        self.sm.add_widget(ConnectionScreen(name='connection'))
        self.sm.add_widget(IPInputScreen(name='ip_input'))
        self.sm.add_widget(NetworkListScreen(name='network_list'))
        return self.sm
    
    def on_start(self):
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([
                    Permission.INTERNET,
                    Permission.ACCESS_NETWORK_STATE,
                    Permission.ACCESS_WIFI_STATE,
                    Permission.CHANGE_WIFI_STATE,
                    Permission.CHANGE_WIFI_MULTICAST_STATE,
                    Permission.ACCESS_FINE_LOCATION,
                    Permission.ACCESS_COARSE_LOCATION,
                    Permission.WAKE_LOCK,
                ])
                print("Permissões solicitadas")
            except Exception as e:
                print(f"Erro permissões: {e}")

    def connect_websocket(self, ip, method):
        url = f"ws://{ip}:8080"
        print(f"Conectando: {url}")
        threading.Thread(
            target=self._ws_thread,
            args=(url, method, ip),
            daemon=True
        ).start()
    
    def _ws_thread(self, url, method, ip):
        try:
            import websocket as ws_lib
            
            def on_open(ws):
                print("Conectado!")
                Clock.schedule_once(lambda dt: self.setup_game(ws, method, ip))
            
            ws = ws_lib.WebSocketApp(url, on_open=on_open)
            ws.run_forever()
        except Exception as e:
            print(f"Erro WS: {e}")

    def setup_game(self, ws, method, ip):
        if 'game' not in [s.name for s in self.sm.screens]:
            screen = Screen(name='game')
            self.layout = MainLayout()
            screen.add_widget(self.layout)
            self.sm.add_widget(screen)
        
        self.layout.ws = ws
        self.layout.connection_info = f"{ip} ({method.upper()})"
        self.sm.current = 'game'

    def disconnect_all(self):
        if hasattr(self, 'layout') and self.layout.ws:
            try:
                self.layout.ws.close()
            except:
                pass
        self.sm.current = 'connection'

if __name__ == '__main__':
    VolantApp().run()
PYTHON_EOF

# Configuração do Buildozer
echo "⚙️  [7/7] Configurando Buildozer..."
buildozer init

# Configura buildozer.spec
cat > buildozer.spec << 'SPEC_EOF'
[app]
title = Volant Controller
package.name = volant
package.domain = org.volant
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy==2.2.0,plyer,websocket-client
orientation = landscape
fullscreen = 1

android.permissions = INTERNET,ACCESS_WIFI_STATE,ACCESS_NETWORK_STATE,CHANGE_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,WAKE_LOCK
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
SPEC_EOF

echo ""
echo "=========================================================="
echo "✅ CONFIGURAÇÃO CONCLUÍDA!"
echo "=========================================================="
echo ""
echo "📱 Para compilar o APK, execute:"
echo "   cd $DIR_NAME"
echo "   source .venv/bin/activate"
echo "   buildozer android debug"
echo ""
echo "🚀 Para compilar E instalar no dispositivo conectado:"
echo "   buildozer android debug deploy run"
echo ""
echo "📦 O APK ficará em: bin/volant-1.0-arm64-v8a-debug.apk"
echo "=========================================================="
