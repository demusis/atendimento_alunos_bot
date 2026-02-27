#!/bin/bash

# ==========================================================
# INSTALADOR DO ASSISTENTE ACADÊMICO PARA RASPBERRY PI 4
# ==========================================================

# Cores para o terminal
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}"
echo "--------------------------------------------------------"
echo "   Iniciando Instalação do Bot Acadêmico no RPi4"
echo "--------------------------------------------------------"
echo -e "${NC}"

# 1. Atualizar repositórios e instalar dependências do sistema
echo -e "📦 1. Instalando dependências do sistema..."
sudo apt update
sudo apt install -y python3-pip python3-venv python3-dev libsqlite3-dev build-essential curl

# 1.5 Instalar Ollama e Modelo de Embedding Local
echo -e "🧠 1.5 Instalando Ollama e Modelo de Embedding..."
if command -v ollama &> /dev/null; then
    echo "Ollama já instalado. Pulando instalação..."
else
    curl -fsSL https://ollama.com/install.sh | sh
    # Aguardar o serviço iniciar
    sleep 5
fi

echo "Baixando modelos de busca local (Nomic e Qwen3)..."
ollama pull nomic-embed-text
ollama pull qwen3-embedding:latest

# 2. Criar ambiente virtual
echo -e "🐍 2. Criando ambiente virtual (venv)..."
if [ -d "venv" ]; then
    echo "Ambiente venv já existe. Pulando criação..."
else
    python3 -m venv venv
fi

# 3. Ativar venv e instalar requisitos do Python
echo -e "🚀 3. Instalando dependências do Python..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3.5 Instalar pysqlite3 (necessário para ChromaDB em algumas distros)
echo -e "🔧 3.5. Verificando compatibilidade do SQLite..."
SQLITE_VERSION=$(python3 -c "import sqlite3; print(sqlite3.sqlite_version)" 2>/dev/null)
SQLITE_MAJOR=$(echo "$SQLITE_VERSION" | cut -d. -f1)
SQLITE_MINOR=$(echo "$SQLITE_VERSION" | cut -d. -f2)

if [ "$SQLITE_MAJOR" -ge 3 ] && [ "$SQLITE_MINOR" -ge 35 ]; then
    echo "✅ SQLite $SQLITE_VERSION é compatível com ChromaDB. pysqlite3 não é necessário."
else
    echo "⚠️ SQLite $SQLITE_VERSION pode ser antigo. Tentando instalar pysqlite3..."
    if pip install pysqlite3-binary 2>/dev/null; then
        echo "✅ pysqlite3-binary instalado com sucesso."
    else
        echo "⚠️ pysqlite3-binary não disponível para esta plataforma. Compilando pysqlite3 do fonte..."
        pip install pysqlite3 2>/dev/null && echo "✅ pysqlite3 compilado com sucesso." || \
            echo "❌ Falha ao instalar pysqlite3. O bot pode não funcionar corretamente com ChromaDB."
    fi
fi

# 4. Criar diretório do Banco de Dados e ajustar permissões
echo -e "⚙️ 4. Configurando diretório do Banco de Dados..."
mkdir -p db_atendimento
chmod 777 db_atendimento

# 5. Inicializar config.json se não existir
if [ ! -f "config.json" ]; then
    echo -e "📝 5. Criando config.json inicial..."
    cp config_example.json config.json
    # Ajusta o caminho do chroma_dir no config.json para o caminho absoluto atual
    FULL_PATH=$(pwd)/db_atendimento
    sed -i "s|\"chroma_dir\": .*|\"chroma_dir\": \"$FULL_PATH\",|g" config.json
fi

# 6. Ajustar permissões e preparativos finais
echo -e "⚙️ 6. Ajustando permissões dos scripts..."
chmod +x start_rp4.sh

# 7. Configurar Auto-Start (systemd)
echo -e "🔄 7. Configurando inicialização automática..."
SERVICE_FILE="telegram-bot.service"
if [ -f "$SERVICE_FILE" ]; then
    # Ajustar caminhos no arquivo de serviço para o diretório e usuário atuais
    CURRENT_DIR=$(pwd)
    CURRENT_USER=$(whoami)
    sed -e "s|WorkingDirectory=.*|WorkingDirectory=$CURRENT_DIR|g" \
        -e "s|ExecStart=.*|ExecStart=$CURRENT_DIR/start_rp4.sh|g" \
        -e "s|User=.*|User=$CURRENT_USER|g" \
        -e "s|/home/[^/]*/\.local/bin|/home/$CURRENT_USER/.local/bin|g" \
        "$SERVICE_FILE" > /tmp/telegram-bot.service
    sudo cp /tmp/telegram-bot.service /etc/systemd/system/telegram-bot.service
    sudo systemctl daemon-reload
    sudo systemctl enable telegram-bot.service
    echo -e "${GREEN}✅ Serviço systemd instalado e habilitado!${NC}"
    echo "   O bot iniciará AUTOMATICAMENTE no boot, sem precisar logar."
    echo "   Para gerenciar: sudo systemctl {start|stop|restart|status} telegram-bot"
    
    # Verificar se está realmente habilitado
    if systemctl is-enabled telegram-bot.service &>/dev/null; then
        echo -e "${GREEN}   ✅ Confirmado: serviço habilitado para auto-start.${NC}"
    else
        echo -e "${RED}   ❌ ERRO: serviço NÃO foi habilitado. Verifique manualmente.${NC}"
    fi
else
    echo -e "${RED}⚠️ Arquivo telegram-bot.service não encontrado. Auto-start não configurado.${NC}"
fi

# 8. Resumo e Instruções
echo -e "${GREEN}"
echo "--------------------------------------------------------"
echo "        ✅ INSTALAÇÃO CONCLUÍDA COM SUCESSO!"
echo "--------------------------------------------------------"
echo -e "${NC}"
echo "Para iniciar o bot agora, use:"
echo "./start_rp4.sh"
echo ""
echo "Para iniciar via systemd:"
echo "sudo systemctl start telegram-bot"
echo ""
echo "Notas Importantes:"
echo "1. Certifique-se de que o seu 'config.json' tem o Token do Telegram e a Key do OpenRouter."
echo "2. O bot rodará em modo CLI (texto) para economizar recursos."
echo "3. O Ollama foi instalado para busca local (RAG) com 'nomic-embed-text' e 'qwen3-embedding'."
echo "4. O bot iniciará automaticamente quando o Raspberry Pi ligar."
echo ""
