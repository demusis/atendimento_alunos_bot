#!/bin/bash

# Script de inicialização para Raspberry Pi 4 com Watchdog
echo "=========================================="
echo "   Iniciando Assistente Acadêmico (CLI)   "
echo "=========================================="

# Muda para o diretório onde o script está localizado
cd "$(dirname "$0")"

# Ativa o ambiente virtual automaticamente
if [ -d "venv" ]; then
    source venv/bin/activate
fi

export PYTHONPATH=$PYTHONPATH:.

# Watchdog: reinicia automaticamente em caso de crash
MAX_RESTARTS=10
RESTART_COUNT=0
COOLDOWN=15  # segundos entre restarts

while [ $RESTART_COUNT -lt $MAX_RESTARTS ]; do
    echo "[Watchdog] Iniciando bot... (tentativa $((RESTART_COUNT + 1))/$MAX_RESTARTS)"
    
    python3 main.py --cli
    EXIT_CODE=$?
    
    # Exit code 0 = encerramento normal (CTRL+C ou /reiniciar_bot)
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[Watchdog] Bot encerrado normalmente (exit 0)."
        break
    fi
    
    RESTART_COUNT=$((RESTART_COUNT + 1))
    echo "[Watchdog] Bot encerrou com código $EXIT_CODE. Reiniciando em ${COOLDOWN}s... ($RESTART_COUNT/$MAX_RESTARTS)"
    sleep $COOLDOWN
done

if [ $RESTART_COUNT -ge $MAX_RESTARTS ]; then
    echo "[Watchdog] ALERTA: Bot crashou $MAX_RESTARTS vezes seguidas. Abortando."
fi

echo "=========================================="
echo "      Bot encerrado.                      "
echo "=========================================="
