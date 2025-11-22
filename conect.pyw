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
        # Obtém o caminho absoluto do interpretador e do script
        executable = sys.executable
        script_path = os.path.abspath(sys.argv[0])
        
        # Monta o comando para o pkexec preservando o ambiente gráfico
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

# Inicialização do UInput (Global)
try:
    ui = UInput(capabilities, name='Gui23x Volant')
except Exception as ex:
    print(f"Erro ao criar UInput: {ex}")
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
        
        # Inicia Broadcast UDP em thread separada (dentro do contexto da thread de servidor)
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
        GLib.idle_add(self.update_callback, f"Cliente conectado: {client_ip}")
        
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
            GLib.idle_add(self.update_callback, f"Cliente desconectado: {client_ip}")

    def stop(self):
        self.running = False
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

# --- INTERFACE GTK ---

class VolantWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Volant Server")
        self.set_border_width(10)
        self.set_default_size(300, 150)
        self.connect("destroy", self.on_close)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(vbox)

        # Label de Status
        self.status_label = Gtk.Label(label="Inicializando...")
        vbox.pack_start(self.status_label, True, True, 0)

        # Lista de Logs Simples
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.log_view)
        scroll.set_min_content_height(100)
        vbox.pack_start(scroll, True, True, 0)

        self.buffer = self.log_view.get_buffer()

        # Botão Sair
        self.button = Gtk.Button(label="Parar Servidor e Sair")
        self.button.connect("clicked", self.on_close)
        vbox.pack_start(self.button, False, False, 0)

        # Inicia Servidor
        self.server_thread = ServerThread(self.update_log)
        self.server_thread.start()

    def update_log(self, message):
        # Atualiza a GUI a partir da thread do servidor
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
        Gtk.main_quit()

if __name__ == "__main__":
    win = VolantWindow()
    win.show_all()
    Gtk.main()
