#!/bin/bash

set -e

if [ "$EUID" -eq 0 ]; then
  echo "Erro: Nao execute como root."
  exit 1
fi

if [ ! -f "main.py" ]; then
    echo "Erro: Arquivo main.py nao encontrado no diretorio atual."
    exit 1
fi

# Diretorio temporario sem espacos para evitar erro do Buildozer
BUILD_DIR="/tmp/volant_build_temp"
ORIGIN_DIR=$(pwd)

echo "Limpando ambientes anteriores..."
rm -rf "$BUILD_DIR"
rm -rf ~/.buildozer

echo "Instalando dependencias do sistema..."
sudo apt update
sudo apt install -y \
    git zip unzip openjdk-17-jdk python3-pip \
    autoconf libtool pkg-config zlib1g-dev \
    libncurses-dev cmake libffi-dev libssl-dev \
    python3-venv libzbar-dev build-essential \
    ccache libltdl-dev

echo "Configurando estrutura de compulacao em $BUILD_DIR..."
mkdir -p "$BUILD_DIR"
cp main.py "$BUILD_DIR/"
cd "$BUILD_DIR"

echo "Configurando ambiente Python..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install Cython==0.29.33 buildozer==1.5.0

echo "Configurando buildozer.spec..."
buildozer init

cat > buildozer.spec << 'SPEC_EOF'
[app]
title = Volant Controller
package.name = volant
package.domain = org.volant
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 2.0.0
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

echo "Iniciando compulacao..."
buildozer -v android debug

echo "Finalizando pacotes..."
APK_ORIGIN=$(find bin -name "*.apk" | head -n 1)

if [ -n "$APK_ORIGIN" ]; then
    cp "$APK_ORIGIN" "$ORIGIN_DIR/Volant Controller.apk"
    echo "Sucesso: 'Volant Controller.apk' gerado em: $ORIGIN_DIR"
    # Limpeza opcional do diretorio temporario
    # rm -rf "$BUILD_DIR"
else
    echo "Erro: Falha na geracao do APK."
    exit 1
fi
