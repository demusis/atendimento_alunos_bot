#!/bin/bash

# Script de inicialização para Raspberry Pi 4
echo "=========================================="
echo "   Iniciando Assistente Acadêmico (CLI)   "
echo "=========================================="

# Ativa o ambiente virtual automaticamente
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Rodar o bot em modo CLI
export PYTHONPATH=$PYTHONPATH:.
python3 main.py --cli

echo "=========================================="
echo "      Bot encerrado com segurança.        "
echo "=========================================="
