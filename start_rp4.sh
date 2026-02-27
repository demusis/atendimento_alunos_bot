#!/bin/bash

# Script de inicialização para Raspberry Pi 4 com Watchdog
echo "=========================================="
echo "   Iniciando Assistente Acadêmico (CLI)   "
echo "=========================================="

# Muda para o diretório onde o script está localizado
cd "$(dirname "$0")"

# --- Proteção contra instância duplicada (PID Lock) ---
LOCKFILE="/tmp/telegram-bot.pid"

# Função de limpeza ao sair
cleanup() {
    echo "[Lock] Removendo lock file..."
    rm -f "$LOCKFILE"
}
trap cleanup EXIT

# Verificar se já existe uma instância rodando
if [ -f "$LOCKFILE" ]; then
    OLD_PID=$(cat "$LOCKFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "=========================================="
        echo "   ❌ ERRO: Bot já está rodando! (PID $OLD_PID)"
        echo "   Use 'sudo systemctl stop telegram-bot' para parar."
        echo "   Ou 'kill $OLD_PID' para encerrar a instância atual."
        echo "=========================================="
        # Não remover o lock file ao sair neste caso
        trap - EXIT
        exit 1
    else
        echo "[Lock] Lock file antigo encontrado (PID $OLD_PID inexistente). Removendo..."
        rm -f "$LOCKFILE"
    fi
fi

# Registrar PID atual
echo $$ > "$LOCKFILE"
echo "[Lock] Instância registrada (PID $$)"

# Ativa o ambiente virtual automaticamente
if [ -d "venv" ]; then
    source venv/bin/activate
fi

export PYTHONPATH=$PYTHONPATH:.

# --- Aguardar conectividade de rede (importante após queda de energia) ---
echo "[Boot] Aguardando conexão com a internet..."
NETWORK_WAIT=0
NETWORK_MAX=60
while [ $NETWORK_WAIT -lt $NETWORK_MAX ]; do
    if ping -c 1 -W 2 api.telegram.org &>/dev/null; then
        echo "[Boot] ✅ Internet disponível após ${NETWORK_WAIT}s."
        break
    fi
    NETWORK_WAIT=$((NETWORK_WAIT + 5))
    echo "[Boot] Sem conexão... aguardando (${NETWORK_WAIT}/${NETWORK_MAX}s)"
    sleep 5
done

if [ $NETWORK_WAIT -ge $NETWORK_MAX ]; then
    echo "[Boot] ⚠️ Internet não disponível após ${NETWORK_MAX}s. Tentando iniciar mesmo assim..."
fi

# --- Aguardar Ollama estar pronto (se instalado) ---
if command -v ollama &>/dev/null; then
    echo "[Boot] Aguardando Ollama..."
    OLLAMA_WAIT=0
    OLLAMA_MAX=90
    while [ $OLLAMA_WAIT -lt $OLLAMA_MAX ]; do
        if ollama list &>/dev/null; then
            echo "[Boot] ✅ Ollama pronto após ${OLLAMA_WAIT}s."
            break
        fi
        OLLAMA_WAIT=$((OLLAMA_WAIT + 5))
        echo "[Boot] Ollama não respondeu... aguardando (${OLLAMA_WAIT}/${OLLAMA_MAX}s)"
        sleep 5
    done
    if [ $OLLAMA_WAIT -ge $OLLAMA_MAX ]; then
        echo "[Boot] ⚠️ Ollama não respondeu após ${OLLAMA_MAX}s. Continuando sem embedding local..."
    fi
fi

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
