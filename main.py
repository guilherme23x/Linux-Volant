import json
import threading
import socket
import math
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.togglebutton import ToggleButton
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.graphics import Color, RoundedRectangle, Ellipse, Line
from kivy.storage.jsonstore import JsonStore

try:
    import websocket

    HAS_WEBSOCKET = True
except ImportError:
    websocket = None
    HAS_WEBSOCKET = False

try:
    from plyer import accelerometer
except ImportError:
    accelerometer = None

if platform != "android":
    Window.size = (960, 540)

KV = """
<ControleBotao>:
    background_normal: ''
    background_down: ''
    background_color: (0, 0, 0, 0)
    canvas.before:
        Color:
            rgba: (0.94, 0.94, 0.94, 1) if self.state == 'normal' else (0.4, 0.4, 0.4, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.height * 0.3]
    canvas.after:
        Color:
            rgba: (0, 0.8, 1, 1) if self.modoEdicao else (0, 0, 0, 0)
        Line:
            width: dp(1.5)
            rectangle: (self.x - dp(2), self.y - dp(2), self.width + dp(4), self.height + dp(4))
    color: (0.13, 0.13, 0.13, 1) if self.state == 'normal' else (1, 1, 1, 1)
    font_size: '16sp'
    bold: True

<ControleToggle>:
    background_normal: ''
    background_down: ''
    background_color: (0, 0, 0, 0)
    canvas.before:
        Color:
            rgba: (0, 0.8, 1, 1) if self.state == 'down' else (0.2, 0.2, 0.2, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.height * 0.3]
    canvas.after:
        Color:
            rgba: (0, 0.8, 1, 1) if self.modoEdicao else (0, 0, 0, 0)
        Line:
            width: dp(1.5)
            rectangle: (self.x - dp(2), self.y - dp(2), self.width + dp(4), self.height + dp(4))
    color: (0.13, 0.13, 0.13, 1) if self.state == 'down' else (0.94, 0.94, 0.94, 1)
    font_size: '14sp'
    bold: True

<GatilhoWidget>:
    orientation: 'vertical'
    min: 0
    max: 255
    value: 0
    size_hint: None, None
    size: dp(50), dp(220)
    canvas.before:
        Color:
            rgba: (0.2, 0.2, 0.2, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]
    canvas.after:
        Color:
            rgba: (0, 0.8, 1, 1) if self.modoEdicao else (0, 0, 0, 0)
        Line:
            width: dp(1.5)
            rectangle: (self.x - dp(2), self.y - dp(2), self.width + dp(4), self.height + dp(4))
    cursor_size: (dp(50), dp(25))
    cursor_image: ''
    value_track: True
    value_track_color: (0.94, 0.94, 0.94, 1)
    value_track_width: dp(50)

<AnalogicoWidget>:
    size_hint: None, None
    size: dp(190), dp(190)
    canvas.before:
        Color:
            rgba: (0.4, 0.4, 0.4, 0.2)
        Ellipse:
            pos: self.pos
            size: self.size
        Color:
            rgba: (0.94, 0.94, 0.94, 0.8)
        Ellipse:
            pos: (self.center_x - dp(35) + self.deslocamento_x, self.center_y - dp(35) + self.deslocamento_y)
            size: dp(70), dp(70)
    canvas.after:
        Color:
            rgba: (0, 0.8, 1, 1) if self.modoEdicao else (0, 0, 0, 0)
        Line:
            width: dp(1.5)
            rectangle: (self.x - dp(2), self.y - dp(2), self.width + dp(4), self.height + dp(4))

<InterfaceConexao>:
    canvas.before:
        Color:
            rgba: (0.13, 0.13, 0.13, 1)
        Rectangle:
            pos: self.pos
            size: self.size
    BoxLayout:
        orientation: 'vertical'
        padding: dp(50)
        spacing: dp(25)
        Label:
            text: "VOLANT CONTROLLER"
            font_size: '36sp'
            color: (0.94, 0.94, 0.94, 1)
            bold: True
        ControleBotao:
            text: "BUSCAR SERVIDORES"
            size_hint_y: 0.2
            on_press: root.manager.current = 'tela_busca'
        ControleBotao:
            text: "CONECTAR VIA USB (CABO)"
            size_hint_y: 0.2
            on_press: app.conectar_servidor('127.0.0.1')
        ControleBotao:
            text: "CONFIGURAR LAYOUT (OFFLINE)"
            size_hint_y: 0.2
            on_press: app.iniciar_modo_offline()

<InterfaceBusca>:
    canvas.before:
        Color:
            rgba: (0.13, 0.13, 0.13, 1)
        Rectangle:
            pos: self.pos
            size: self.size
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        Label:
            text: "DISPOSITIVOS NA REDE"
            size_hint_y: 0.1
            color: (0.94, 0.94, 0.94, 1)
            bold: True
        ScrollView:
            GridLayout:
                id: lista_dispositivos
                cols: 1
                spacing: dp(10)
                size_hint_y: None
                height: self.minimum_height
        BoxLayout:
            size_hint_y: 0.15
            spacing: dp(10)
            ControleBotao:
                text: "ATUALIZAR"
                on_press: root.iniciar_busca()
            ControleBotao:
                text: "VOLTAR"
                on_press: root.manager.current = 'tela_conexao'

<InterfacePrincipal>:
    canvas.before:
        Color:
            rgba: (0.13, 0.13, 0.13, 1)
        Rectangle:
            pos: self.pos
            size: self.size
    FloatLayout:
        id: area_controles
    
    BoxLayout:
        size_hint: 1, 0.12
        pos_hint: {'top': 1}
        padding: [dp(15), dp(8)]
        spacing: dp(15)
        
        Label:
            text: root.infoConexao
            color: (0.94, 0.94, 0.94, 0.5)
            halign: 'left'
            text_size: self.size
            valign: 'middle'
            size_hint_x: 0.5

        Widget:
            size_hint_x: 0.38

        ControleBotao:
            text: "SALVAR" if root.modoEdicaoAtivo else "EDITAR"
            size_hint_x: 0.12
            on_press: root.salvar_layout() if root.modoEdicaoAtivo else root.alternar_edicao(True)
"""


class GatilhoWidget(Slider):
    modoEdicao = BooleanProperty(False)

    def __init__(self, identificador, callback, **kwargs):
        super().__init__(**kwargs)
        self.identificador = identificador
        self.callback = callback

    def on_value(self, instance, value):
        if not self.modoEdicao:
            self.callback("abs", self.identificador, int(value))

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if self.modoEdicao:
                touch.grab(self)
                return True
            return super().on_touch_down(touch)
        return False

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            if self.modoEdicao:
                self.pos_hint = {
                    "center_x": touch.x / self.parent.width,
                    "center_y": touch.y / self.parent.height,
                }
                return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            if self.modoEdicao:
                touch.ungrab(self)
                return True
            else:
                res = super().on_touch_up(touch)
                self.value = 0
                return res
        return super().on_touch_up(touch)


class AnalogicoWidget(FloatLayout):
    deslocamento_x = NumericProperty(0)
    deslocamento_y = NumericProperty(0)
    modoEdicao = BooleanProperty(False)

    def __init__(self, identificador, callback, **kwargs):
        super().__init__(**kwargs)
        self.identificador = identificador
        self.callback = callback
        self.raio_max = dp(65)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            if not self.modoEdicao:
                self.atualizar_posicao(touch)
            return True
        return False

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            if self.modoEdicao:
                self.pos_hint = {
                    "center_x": touch.x / self.parent.width,
                    "center_y": touch.y / self.parent.height,
                }
            else:
                self.atualizar_posicao(touch)
            return True
        return False

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            if not self.modoEdicao:
                self.deslocamento_x = 0
                self.deslocamento_y = 0
                self.callback(self.identificador, 0, 0)
            return True
        return False

    def atualizar_posicao(self, touch):
        dx = touch.x - self.center_x
        dy = touch.y - self.center_y
        distancia = math.sqrt(dx**2 + dy**2)

        if distancia > self.raio_max:
            escala = self.raio_max / distancia
            dx *= escala
            dy *= escala

        self.deslocamento_x = dx
        self.deslocamento_y = dy

        # Correção da escala para compatibilidade com conect.py (limite de 255)
        norm_x = (dx / self.raio_max) * 255
        # Inversão do eixo Y (Kivy possui Y positivo para cima, evdev possui Y negativo para cima)
        norm_y = -(dy / self.raio_max) * 255

        self.callback(self.identificador, int(norm_x), int(norm_y))


class ControleBotao(Button):
    modoEdicao = BooleanProperty(False)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if self.modoEdicao:
                touch.grab(self)
                return True
            return super().on_touch_down(touch)
        return False

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            if self.modoEdicao:
                self.pos_hint = {
                    "center_x": touch.x / self.parent.width,
                    "center_y": touch.y / self.parent.height,
                }
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            if self.modoEdicao:
                touch.ungrab(self)
                return True
        return super().on_touch_up(touch)


class ControleToggle(ToggleButton):
    modoEdicao = BooleanProperty(False)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if self.modoEdicao:
                touch.grab(self)
                return True
            return super().on_touch_down(touch)
        return False

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            if self.modoEdicao:
                self.pos_hint = {
                    "center_x": touch.x / self.parent.width,
                    "center_y": touch.y / self.parent.height,
                }
                return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            if self.modoEdicao:
                touch.ungrab(self)
                return True
        return super().on_touch_up(touch)


class InterfaceConexao(Screen):
    pass


class InterfaceBusca(Screen):
    def on_enter(self):
        self.iniciar_busca()

    def iniciar_busca(self):
        self.ids.lista_dispositivos.clear_widgets()
        threading.Thread(target=self._executar_scan, daemon=True).start()

    def _executar_scan(self):
        encontrados = []
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", 5000))
            sock.settimeout(2.0)
            for _ in range(5):
                try:
                    data, addr = sock.recvfrom(1024)
                    ip = addr[0]
                    if ip not in encontrados:
                        encontrados.append(ip)
                        Clock.schedule_once(lambda dt, i=ip: self.adicionar_item(i))
                except socket.timeout:
                    break
            sock.close()
        except:
            pass

    def adicionar_item(self, ip):
        btn = ControleBotao(text=f"Servidor: {ip}", size_hint_y=None, height=dp(80))
        btn.bind(on_release=lambda x: App.get_running_app().conectar_servidor(ip))
        self.ids.lista_dispositivos.add_widget(btn)


class InterfacePrincipal(Screen):
    infoConexao = StringProperty("Offline")
    modoEdicaoAtivo = BooleanProperty(False)
    giroscopioAtivo = False
    last_tilt = 0.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.store = JsonStore("layout_config.json")
        self.configurar_controles()

    def obter_posicao(self, key, default_x, default_y):
        if self.store.exists(key):
            pos = self.store.get(key)
            return pos["x"], pos["y"]
        return default_x, default_y

    def configurar_controles(self):
        botoes = [
            ("A", 0.88, 0.15, "BTN_A"),
            ("B", 0.94, 0.28, "BTN_B"),
            ("X", 0.82, 0.28, "BTN_NORTH"),
            ("Y", 0.88, 0.41, "BTN_WEST"),
            ("LB", 0.15, 0.88, "BTN_TL"),
            ("RB", 0.85, 0.88, "BTN_TR"),
            ("SEL", 0.43, 0.08, "BTN_SELECT"),
            ("STR", 0.57, 0.08, "BTN_START"),
        ]

        dpad = [
            ("↑", 0.22, 0.38, "ABS_HAT0Y", -1),
            ("↓", 0.22, 0.12, "ABS_HAT0Y", 1),
            ("←", 0.12, 0.25, "ABS_HAT0X", -1),
            ("→", 0.32, 0.25, "ABS_HAT0X", 1),
        ]

        for t, px, py, c in botoes:
            cx, cy = self.obter_posicao(t, px, py)
            btn = ControleBotao(
                text=t,
                size_hint=(0.08, 0.13),
                pos_hint={"center_x": cx, "center_y": cy},
            )
            btn.store_key = t
            btn.bind(on_press=lambda inst, code=c: self.enviar("key", code, 1))
            btn.bind(on_release=lambda inst, code=c: self.enviar("key", code, 0))
            self.ids.area_controles.add_widget(btn)

        for t, px, py, c, v in dpad:
            cx, cy = self.obter_posicao(t, px, py)
            btn = ControleBotao(
                text=t,
                size_hint=(0.08, 0.13),
                pos_hint={"center_x": cx, "center_y": cy},
            )
            btn.store_key = t
            btn.bind(on_press=lambda inst, code=c, val=v: self.enviar("abs", code, val))
            btn.bind(on_release=lambda inst, code=c: self.enviar("abs", code, 0))
            self.ids.area_controles.add_widget(btn)

        cx, cy = self.obter_posicao("analogMain", 0.18, 0.58)
        self.analogMain = AnalogicoWidget(
            "main", self.enviar_an, pos_hint={"center_x": cx, "center_y": cy}
        )
        self.analogMain.store_key = "analogMain"

        cx, cy = self.obter_posicao("analogCam", 0.82, 0.58)
        self.analogCam = AnalogicoWidget(
            "cam", self.enviar_an, pos_hint={"center_x": cx, "center_y": cy}
        )
        self.analogCam.store_key = "analogCam"

        self.ids.area_controles.add_widget(self.analogMain)
        self.ids.area_controles.add_widget(self.analogCam)

        cx, cy = self.obter_posicao("gatilhoLT", 0.05, 0.50)
        self.gatilhoLT = GatilhoWidget(
            "ABS_Z", self.enviar, pos_hint={"center_x": cx, "center_y": cy}
        )
        self.gatilhoLT.store_key = "gatilhoLT"

        cx, cy = self.obter_posicao("gatilhoRT", 0.95, 0.50)
        self.gatilhoRT = GatilhoWidget(
            "ABS_RZ", self.enviar, pos_hint={"center_x": cx, "center_y": cy}
        )
        self.gatilhoRT.store_key = "gatilhoRT"

        self.ids.area_controles.add_widget(self.gatilhoLT)
        self.ids.area_controles.add_widget(self.gatilhoRT)

        cx, cy = self.obter_posicao("btn_giro", 0.5, 0.4)
        self.btn_giro = ControleToggle(
            text="VOLANTE",
            size_hint=(0.15, 0.12),
            pos_hint={"center_x": cx, "center_y": cy},
        )
        self.btn_giro.store_key = "btn_giro"
        self.btn_giro.bind(
            state=lambda inst, val: self.toggle_giroscopio(val == "down")
        )
        self.ids.area_controles.add_widget(self.btn_giro)

    def alternar_edicao(self, estado):
        self.modoEdicaoAtivo = estado
        for c in self.ids.area_controles.children:
            if hasattr(c, "modoEdicao"):
                c.modoEdicao = estado

    def salvar_layout(self):
        for c in self.ids.area_controles.children:
            wid = getattr(c, "store_key", None)
            if wid and "center_x" in c.pos_hint and "center_y" in c.pos_hint:
                self.store.put(wid, x=c.pos_hint["center_x"], y=c.pos_hint["center_y"])
        self.alternar_edicao(False)

    def toggle_giroscopio(self, estado):
        self.giroscopioAtivo = estado
        if estado:
            self.last_tilt = 0.0
            try:
                if accelerometer:
                    accelerometer.enable()
                    Clock.schedule_interval(self.update_giro, 1.0 / 60.0)
            except:
                pass
        else:
            Clock.unschedule(self.update_giro)
            self.enviar("abs", "ABS_X", 0)

    def update_giro(self, dt):
        if not self.giroscopioAtivo or not accelerometer:
            return
        try:
            acc = accelerometer.acceleration
            if acc:
                y = acc[1]
                # Correção da escala para compatibilidade com conect.py (limite de 255)
                alvo = (max(min(y, 7.0), -7.0) / 7.0) * 255
                self.last_tilt = (0.3 * alvo) + (0.7 * self.last_tilt)
                self.enviar("abs", "ABS_X", int(self.last_tilt))
        except:
            pass

    def enviar(self, t, c, v):
        App.get_running_app().enviar_socket({"type": t, "code": c, "value": v})

    def enviar_an(self, id_an, x, y):
        px = "ABS_X" if id_an == "main" else "ABS_RX"
        py = "ABS_Y" if id_an == "main" else "ABS_RY"
        if not (id_an == "main" and self.giroscopioAtivo):
            self.enviar("abs", px, x)
        self.enviar("abs", py, y)


class VolantApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ws = None
        self.eixos = {}
        self.eixos_sujos = set()
        self.botoes_queue = []

    def build(self):
        self.sm = ScreenManager()
        self.sm.add_widget(InterfaceConexao(name="tela_conexao"))
        self.sm.add_widget(InterfaceBusca(name="tela_busca"))
        self.interfacePrincipal = InterfacePrincipal(name="tela_principal")
        self.sm.add_widget(self.interfacePrincipal)

        Clock.schedule_interval(self._enviar_loop, 1.0 / 60.0)
        return self.sm

    def iniciar_modo_offline(self):
        self.interfacePrincipal.infoConexao = "MODO CONFIGURAÇÃO"
        self.interfacePrincipal.alternar_edicao(True)
        self.sm.current = "tela_principal"

    def conectar_servidor(self, ip):
        if not HAS_WEBSOCKET:
            return
        threading.Thread(target=self._tarefa_conexao, args=(ip,), daemon=True).start()

    def _tarefa_conexao(self, ip):
        try:
            self.ws = websocket.create_connection(f"ws://{ip}:8080", timeout=5)
            self.ws.settimeout(None)
            Clock.schedule_once(lambda dt: self._on_connected(ip))
            threading.Thread(target=self._receber_loop, daemon=True).start()
        except:
            pass

    def _receber_loop(self):
        while self.ws:
            try:
                self.ws.recv()
            except:
                Clock.schedule_once(lambda dt: self.fechar_conexao())
                break

    def _on_connected(self, ip):
        self.interfacePrincipal.infoConexao = f"SERVIDOR: {ip}"
        self.sm.current = "tela_principal"

    def enviar_socket(self, payload):
        t = payload.get("type")
        c = payload.get("code")
        v = payload.get("value")

        if t == "abs":
            self.eixos[c] = v
            self.eixos_sujos.add(c)
        else:
            self.botoes_queue.append(payload)

    def _enviar_loop(self, dt):
        if not self.ws:
            return

        try:
            for msg in self.botoes_queue:
                self.ws.send(json.dumps(msg))
            self.botoes_queue.clear()

            for c in list(self.eixos_sujos):
                msg = {"type": "abs", "code": c, "value": self.eixos[c]}
                self.ws.send(json.dumps(msg))
            self.eixos_sujos.clear()

        except:
            self.fechar_conexao()

    def fechar_conexao(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None

        self.eixos_sujos.clear()
        self.botoes_queue.clear()
        self.interfacePrincipal.alternar_edicao(False)
        self.sm.current = "tela_conexao"


if __name__ == "__main__":
    Builder.load_string(KV)
    VolantApp().run()
