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

# 4. Ajustar permissões e preparativos finais
echo -e "⚙️ 4. Ajustando permissões..."
chmod +x start_rp4.sh

# 5. Resumo e Instruções
echo -e "${GREEN}"
echo "--------------------------------------------------------"
echo "        ✅ INSTALAÇÃO CONCLUÍDA COM SUCESSO!"
echo "--------------------------------------------------------"
echo -e "${NC}"
echo "Para iniciar o bot agora, use:"
echo "./start_rp4.sh"
echo ""
echo "Notas Importantes:"
echo "1. Certifique-se de que o seu 'config.json' tem o Token do Telegram e a Key do OpenRouter."
echo "2. O bot rodará em modo CLI (texto) para economizar recursos."
echo "3. Se encontrar erros com o SQLite, o 'pysqlite3-binary' já foi incluído para corrigir."
echo ""
