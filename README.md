
<img width="1366" height="720" alt="Controller and Server" src="https://github.com/user-attachments/assets/7d6b5ace-5861-4d67-b3ab-d99d04e4a011" />


# Volant Controller

Emula um gamepad físico no Linux usando um dispositivo Android. Converte toque e dados do acelerômetro em eventos de kernel via `uinput`.

<details>
<summary><strong>📋 Arquitetura</strong></summary>

* **Servidor (Linux):** `conect.pyw` (root) gere a rede e cria o dispositivo virtual.
* **Cliente (Android):** App Kivy (`main.py`) transmite inputs via WebSocket.

**Protocolo:**
* **Descoberta:** Broadcast UDP (Porta 5000).
* **Dados:** JSON via WebSocket (Porta 8080) mapeando `EV_KEY` e `EV_ABS`.

</details>

<details>
<summary><strong>🐧 Servidor (Linux)</strong></summary>

Traduz pacotes JSON em interrupções de hardware simuladas.

* **Requisitos:** Python 3, `evdev`, `websockets`, `asyncio`, `PyGObject`.
* **Uso:** `python3 conect.pyw` (Auto-elevação via `pkexec` para acesso ao `/dev/uinput`). Exibe logs em GUI GTK.

</details>

<details>
<summary><strong>📱 Cliente (Android Build)</strong></summary>

Compilação automatizada via `Buildozer` e `script.sh` (Debian/Ubuntu).

**O script `script.sh` executa:**
1.  Limpeza e instalação de dependências (JDK, Python, libs C).
2.  Configuração de venv, `Cython` e `Buildozer`.
3.  Geração do `main.py` e `buildozer.spec`.

**Comandos:**
```bash
chmod +x script.sh && ./script.sh
cd VolantController && source .venv/bin/activate
buildozer android debug  # APK gerado em bin/
