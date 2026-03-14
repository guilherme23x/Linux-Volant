#!/bin/bash

# ============================================================
# GERADOR DE PACOTE .DEB - VOLANT SERVER (CORREÇÃO DE ÍCONE)
# ============================================================

APP_NAME="volant-server"
VERSION="1.0"
ARCH="all"
MAINTAINER="Voce <seu@email.com>"
DESC="Servidor de Controle Volant via WebSocket e UInput"
ICON_FILE="icon.svg"  # Certifique-se que este arquivo existe

# Verificação do Ícone
if [ ! -f "$ICON_FILE" ]; then
    echo "❌ ERRO: O arquivo '$ICON_FILE' não foi encontrado."
    exit 1
fi

BUILD_DIR="${APP_NAME}_${VERSION}_${ARCH}"

echo "🔨 [1/7] Limpando área de trabalho..."
rm -rf "$BUILD_DIR"
rm -f "${APP_NAME}_${VERSION}_${ARCH}.deb"

echo "📂 [2/7] Criando diretórios..."
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/share/$APP_NAME"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/pixmaps"

echo "🎨 [3/7] Instalando ícone..."
cp "$ICON_FILE" "$BUILD_DIR/usr/share/pixmaps/$APP_NAME.svg"

echo "📝 [4/7] Configurando dependências..."
cat > "$BUILD_DIR/DEBIAN/control" << EOF
Package: $APP_NAME
Version: $VERSION
Architecture: $ARCH
Maintainer: $MAINTAINER
Depends: python3, python3-gi, python3-evdev, python3-websockets, policykit-1, gir1.2-rsvg-2.0
Section: utils
Priority: optional
Description: $DESC
 Servidor para Joystick Virtual.
EOF

echo "🐍 [5/7] Gerando código Python..."
cat > "$BUILD_DIR/usr/share/$APP_NAME/conect.py" << 'PYTHON_EOF'
#!/usr/bin/env python3
import sys
import os
import subprocess
import socket
import time
import json
import threading
import asyncio
import websockets
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from evdev import UInput, ecodes as e, AbsInfo

# --- AUTO ELEVAÇÃO PARA ROOT ---
def check_root():
    if os.geteuid() != 0:
        executable = sys.executable
        script_path = os.path.abspath(sys.argv[0])
        
        cmd = [
            'pkexec',
            'env',
            f'DISPLAY={os.environ.get("DISPLAY", ":0")}',
            f'XAUTHORITY={os.environ.get("XAUTHORITY", "")}',
            executable,
            script_path
        ]
        
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError:
            print("Falha na elevação de privilégios.")
        sys.exit(0)

check_root()

# --- CONFIGURAÇÕES ---
BROADCAST_PORT = 5000
WEBSOCKET_PORT = 8080
DEVICE_NAME = "Microsoft X-Box 360 pad"

# Configuração COMPLETA para emular Xbox 360 Controller
# Ranges corretos para cada eixo
ABS_RANGE_STICK = AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)
ABS_RANGE_TRIGGER = AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)
ABS_RANGE_DPAD = AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)

# Capabilities EXATAS de um Xbox 360 Controller
capabilities = {
    e.EV_KEY: [
        e.BTN_SOUTH,    # A
        e.BTN_EAST,     # B
        e.BTN_NORTH,    # X
        e.BTN_WEST,     # Y
        e.BTN_TL,       # LB
        e.BTN_TR,       # RB
        e.BTN_SELECT,   # Back/Select
        e.BTN_START,    # Start
        e.BTN_MODE,     # Xbox/Guide
        e.BTN_THUMBL,   # Left Stick Click
        e.BTN_THUMBR,   # Right Stick Click
    ],
    e.EV_ABS: [
        (e.ABS_X, ABS_RANGE_STICK),       # Left Stick X
        (e.ABS_Y, ABS_RANGE_STICK),       # Left Stick Y
        (e.ABS_RX, ABS_RANGE_STICK),      # Right Stick X
        (e.ABS_RY, ABS_RANGE_STICK),      # Right Stick Y
        (e.ABS_Z, ABS_RANGE_TRIGGER),     # LT (Left Trigger)
        (e.ABS_RZ, ABS_RANGE_TRIGGER),    # RT (Right Trigger)
        (e.ABS_HAT0X, ABS_RANGE_DPAD),    # D-Pad X
        (e.ABS_HAT0Y, ABS_RANGE_DPAD),    # D-Pad Y
    ]
}

# Mapeamento de códigos alternativos para Xbox 360
BUTTON_MAP = {
    'BTN_A': e.BTN_SOUTH,
    'BTN_B': e.BTN_EAST,
    'BTN_X': e.BTN_WEST,
    'BTN_Y': e.BTN_NORTH,
    'BTN_NORTH': e.BTN_NORTH,
    'BTN_SOUTH': e.BTN_SOUTH,
    'BTN_EAST': e.BTN_EAST,
    'BTN_WEST': e.BTN_WEST,
    'BTN_TL': e.BTN_TL,
    'BTN_TR': e.BTN_TR,
    'BTN_SELECT': e.BTN_SELECT,
    'BTN_START': e.BTN_START,
    'BTN_MODE': e.BTN_MODE,
    'BTN_THUMBL': e.BTN_THUMBL,
    'BTN_THUMBR': e.BTN_THUMBR,
}

# Inicialização do UInput com vendor/product IDs do Xbox 360
try:
    ui = UInput(
        capabilities, 
        name=DEVICE_NAME,
        vendor=0x045e,   # Microsoft
        product=0x028e,  # Xbox 360 Controller
        version=0x110,
        bustype=0x03     # USB
    )
    print(f"✅ Dispositivo criado: {DEVICE_NAME}")
    print(f"   Vendor: 0x045e (Microsoft)")
    print(f"   Product: 0x028e (Xbox 360 Controller)")
except Exception as ex:
    print(f"❌ Erro ao criar UInput: {ex}")
    sys.exit(1)

# --- LÓGICA DE REDE ---

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

class ServerThread(threading.Thread):
    def __init__(self, update_callback):
        super().__init__()
        self.update_callback = update_callback
        self.running = True
        self.loop = None

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        threading.Thread(target=self.broadcast_presence, daemon=True).start()
        
        local_ip = get_local_ip()
        GLib.idle_add(self.update_callback, f"🎮 Xbox 360 Controller Virtual")
        GLib.idle_add(self.update_callback, f"📡 IP: {local_ip}:{WEBSOCKET_PORT}")
        
        start_server = websockets.serve(self.handler, "0.0.0.0", WEBSOCKET_PORT)
        self.loop.run_until_complete(start_server)
        self.loop.run_forever()

    def broadcast_presence(self):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        my_ip = get_local_ip()
        payload = json.dumps({
            "name": "Xbox 360 Controller",
            "ip": my_ip,
            "port": WEBSOCKET_PORT,
            "type": "volant_server"
        }).encode('utf-8')
        
        while self.running:
            try:
                udp_socket.sendto(payload, ('<broadcast>', BROADCAST_PORT))
                time.sleep(2)
            except Exception:
                time.sleep(5)

    async def handler(self, websocket):
        client_ip = websocket.remote_address[0]
        GLib.idle_add(self.update_callback, f"✅ Conectado: {client_ip}")
        
        try:
            async for message in websocket:
                data = json.loads(message)
                code_str = data.get('code')
                value = int(data.get('value', 0))
                msg_type = data.get('type')
                
                # Processa botões
                if msg_type == 'key':
                    if code_str in BUTTON_MAP:
                        code = BUTTON_MAP[code_str]
                        ui.write(e.EV_KEY, code, value)
                        ui.syn()
                    elif hasattr(e, code_str):
                        code = getattr(e, code_str)
                        ui.write(e.EV_KEY, code, value)
                        ui.syn()
                
                # Processa eixos analógicos
                elif msg_type == 'abs':
                    if hasattr(e, code_str):
                        code = getattr(e, code_str)
                        
                        # Converte valores para ranges corretos
                        if code in [e.ABS_X, e.ABS_Y, e.ABS_RX, e.ABS_RY]:
                            # Analógicos: converte -255~255 para -32768~32767
                            normalized_value = int((value / 255.0) * 32767)
                        elif code in [e.ABS_Z, e.ABS_RZ]:
                            # Gatilhos: 0~255 (já está correto)
                            normalized_value = value
                        elif code in [e.ABS_HAT0X, e.ABS_HAT0Y]:
                            # D-Pad: -1, 0, 1 (já está correto)
                            normalized_value = value
                        else:
                            normalized_value = value
                        
                        ui.write(e.EV_ABS, code, normalized_value)
                        ui.syn()
                        
        except Exception as ex:
            print(f"Handler error: {ex}")
        finally:
            GLib.idle_add(self.update_callback, f"❌ Desconectado: {client_ip}")

    def stop(self):
        self.running = False
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

# --- INTERFACE GTK ---

class VolantWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Xbox 360 Virtual Controller")
        self.set_border_width(10)
        self.set_default_size(400, 250)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("destroy", self.on_close)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(vbox)

        # Header
        header = Gtk.Label()
        header.set_markup("<b><big>🎮 Xbox 360 Controller Virtual</big></b>")
        vbox.pack_start(header, False, False, 5)

        # Status Label
        self.status_label = Gtk.Label(label="Inicializando servidor...")
        vbox.pack_start(self.status_label, False, False, 0)

        # Log View
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD)
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.log_view)
        vbox.pack_start(scroll, True, True, 0)

        self.buffer = self.log_view.get_buffer()

        # Botão Sair
        self.button = Gtk.Button(label="🛑 Parar Servidor")
        self.button.connect("clicked", self.on_close)
        vbox.pack_start(self.button, False, False, 0)

        # Inicia Servidor
        self.server_thread = ServerThread(self.update_log)
        self.server_thread.start()

    def update_log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        text = f"[{timestamp}] {message}\n"
        end_iter = self.buffer.get_end_iter()
        self.buffer.insert(end_iter, text)
        
        # Auto-scroll
        adj = self.log_view.get_parent().get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())
        return False

    def on_close(self, widget):
        self.server_thread.stop()
        ui.close()
        Gtk.main_quit()

if __name__ == "__main__":
    win = VolantWindow()
    win.show_all()
    Gtk.main()

PYTHON_EOF

chmod +x "$BUILD_DIR/usr/share/$APP_NAME/conect.py"

echo "🚀 [6/7] Criando lançadores..."
cat > "$BUILD_DIR/usr/bin/$APP_NAME" << EOF
#!/bin/bash
/usr/share/$APP_NAME/conect.py
EOF
chmod +x "$BUILD_DIR/usr/bin/$APP_NAME"

# Criação do .desktop com StartupWMClass
cat > "$BUILD_DIR/usr/share/applications/$APP_NAME.desktop" << EOF
[Desktop Entry]
Name=Volant Server
Comment=Servidor para Joystick Virtual Android
Exec=/usr/bin/$APP_NAME
Icon=$APP_NAME
Terminal=false
Type=Application
Categories=Utility;Game;
StartupNotify=true
# ESTA LINHA ABAIXO GARANTE QUE O ÍCONE APAREÇA NA BARRA DE TAREFAS
StartupWMClass=volant-server
EOF

echo "📦 [7/7] Gerando .deb..."
dpkg-deb --build "$BUILD_DIR" "${APP_NAME}_${VERSION}_${ARCH}.deb"

echo ""
echo "✅ PRONTO! Ícone corrigido."
echo "   Instale com: sudo apt install ./${APP_NAME}_${VERSION}_${ARCH}.deb"
