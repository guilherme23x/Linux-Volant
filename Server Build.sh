#!/bin/bash

# ============================================================
# GERADOR DE PACOTE .DEB - VOLANT SERVER (SEPARADO)
# ============================================================

APP_NAME="volant-server"
VERSION="2.0"
ARCH="all"
MAINTAINER="Gui23x guigomes4330@gmail.com"
DESC="Servidor de Controle Volant via WebSocket e UInput"

ICON_FILE="icon.svg"           # Ícone na mesma pasta
PYTHON_FILE="main-server.py"   # Script Python na mesma pasta

# Verificação do Ícone
if [ ! -f "$ICON_FILE" ]; then
    echo "❌ ERRO: O arquivo '$ICON_FILE' não foi encontrado nesta pasta."
    exit 1
fi

# Verificação do Script Python
if [ ! -f "$PYTHON_FILE" ]; then
    echo "❌ ERRO: O arquivo '$PYTHON_FILE' não foi encontrado nesta pasta."
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

echo "🐍 [5/7] Copiando código Python..."
cp "$PYTHON_FILE" "$BUILD_DIR/usr/share/$APP_NAME/main-server.py"
chmod +x "$BUILD_DIR/usr/share/$APP_NAME/main-server.py"

echo "🚀 [6/7] Criando lançadores..."
cat > "$BUILD_DIR/usr/bin/$APP_NAME" << EOF
#!/bin/bash
/usr/share/$APP_NAME/main-server.py
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
echo "✅ PRONTO! Pacote gerado com sucesso."
echo "   Instale com: sudo apt install ./${APP_NAME}_${VERSION}_${ARCH}.deb"
