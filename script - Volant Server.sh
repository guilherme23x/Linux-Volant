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
from gi.repository import Gtk, GLib, Gdk
from evdev import UInput, ecodes as e, AbsInfo

# --- CORREÇÃO DO ÍCONE NA BARRA DE TAREFAS ---
# Define o nome do programa para o sistema reconhecer o .desktop correto
GLib.set_prgname("volant-server")

ICON_PATH = "/usr/share/pixmaps/volant-server.svg"

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
DEVICE_NAME = "Volant-PC-Gui"
ABS_RANGE = AbsInfo(0, -255, 255, 0, 0, 0)

capabilities = {
    e.EV_KEY: [e.BTN_A, e.BTN_B, e.BTN_X, e.BTN_Y, e.BTN_TL, e.BTN_TR, e.BTN_START, e.BTN_SELECT],
    e.EV_ABS: [(e.ABS_X, ABS_RANGE), (e.ABS_Y, ABS_RANGE), (e.ABS_RX, ABS_RANGE), (e.ABS_RZ, ABS_RANGE), (e.ABS_Z, ABS_RANGE)]
}

try:
    ui = UInput(capabilities, name='Gui23x Volant')
except Exception as ex:
    print(f"Erro ao criar UInput: {ex}")
    sys.exit(1)

# --- REDE ---
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
        GLib.idle_add(self.update_callback, f"Ouvindo em: {local_ip}:{WEBSOCKET_PORT}")
        
        start_server = websockets.serve(self.handler, "0.0.0.0", WEBSOCKET_PORT)
        self.loop.run_until_complete(start_server)
        self.loop.run_forever()

    def broadcast_presence(self):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        my_ip = get_local_ip()
        payload = json.dumps({
            "name": DEVICE_NAME,
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
        GLib.idle_add(self.update_callback, f"Cliente: {client_ip}")
        try:
            async for message in websocket:
                data = json.loads(message)
                if hasattr(e, data['code']):
                    code = getattr(e, data['code'])
                    val = int(data['value'])
                    if data['type'] == 'key':
                        ui.write(e.EV_KEY, code, val)
                    elif data['type'] == 'abs':
                        ui.write(e.EV_ABS, code, val)
                    ui.syn()
        except Exception:
            pass
        finally:
            GLib.idle_add(self.update_callback, f"Desconectado: {client_ip}")

    def stop(self):
        self.running = False
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

# --- GUI ---
class VolantWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Volant Server")
        self.set_border_width(10)
        self.set_default_size(350, 200)
        self.connect("destroy", self.on_close)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        # Define a Classe da Janela para o Dock reconhecer o ícone
        self.set_wmclass("volant-server", "Volant Server")
        
        if os.path.exists(ICON_PATH):
            try:
                self.set_icon_from_file(ICON_PATH)
            except Exception as e:
                print(f"Icon error: {e}")

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(vbox)

        self.status_label = Gtk.Label(label="<b>Volant Server Ativo</b>")
        self.status_label.set_use_markup(True)
        vbox.pack_start(self.status_label, False, False, 5)

        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.log_view)
        vbox.pack_start(scroll, True, True, 0)

        self.buffer = self.log_view.get_buffer()

        self.button = Gtk.Button(label="Parar Servidor")
        self.button.connect("clicked", self.on_close)
        vbox.pack_start(self.button, False, False, 5)

        self.server_thread = ServerThread(self.update_log)
        self.server_thread.start()

    def update_log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        text = f"[{timestamp}] {message}\n"
        end_iter = self.buffer.get_end_iter()
        self.buffer.insert(end_iter, text)
        adj = self.log_view.get_parent().get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())
        return False

    def on_close(self, widget):
        self.server_thread.stop()
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
