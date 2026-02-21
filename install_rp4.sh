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
sudo apt install -y python3-pip python3-venv python3-dev libsqlite3-dev build-essential

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
    sed -i "s|\"chroma_dir\": .*|\"chroma_dir\": \"$FULL_PATH\"|g" config.json
fi

# 6. Ajustar permissões e preparativos finais
echo -e "⚙️ 6. Ajustando permissões dos scripts..."
chmod +x start_rp4.sh

# 7. Configurar Auto-Start (systemd)
echo -e "🔄 7. Configurando inicialização automática..."
SERVICE_FILE="telegram-bot.service"
if [ -f "$SERVICE_FILE" ]; then
    # Ajustar caminhos no arquivo de serviço
    CURRENT_DIR=$(pwd)
    CURRENT_USER=$(whoami)
    sed "s|/home/pi/atendimento_alunos_bot|$CURRENT_DIR|g; s|User=pi|User=$CURRENT_USER|g" \
        "$SERVICE_FILE" > /tmp/telegram-bot.service
    sudo cp /tmp/telegram-bot.service /etc/systemd/system/telegram-bot.service
    sudo systemctl daemon-reload
    sudo systemctl enable telegram-bot.service
    echo -e "${GREEN}✅ Serviço systemd instalado! O bot iniciará automaticamente no boot.${NC}"
    echo "   Para gerenciar: sudo systemctl {start|stop|restart|status} telegram-bot"
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
echo "3. Se encontrar erros com o SQLite, o 'pysqlite3-binary' já foi incluído para corrigir."
echo "4. O bot iniciará automaticamente quando o Raspberry Pi ligar."
echo ""
