#!/bin/bash

# ==========================================================
# MONITOR DO BOT - Exibe logs em tempo real no terminal
# ==========================================================

# Cores
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Diretório do bot
BOT_DIR="$(dirname "$0")"
LOG_FILE="$BOT_DIR/bot.log"

show_help() {
    echo -e "${GREEN}"
    echo "=========================================="
    echo "   📡 Monitor do Bot - Assistente Acadêmico"
    echo "=========================================="
    echo -e "${NC}"
    echo ""
    echo "Uso: ./monitor_rp4.sh [opção]"
    echo ""
    echo "Opções:"
    echo "  (sem argumento)  Mostra logs do bot.log em tempo real (tail -f)"
    echo "  --journal        Mostra logs do systemd (journalctl)"
    echo "  --full           Mostra AMBOS (journal + bot.log) intercalados"
    echo "  --status         Mostra status do serviço e últimas 30 linhas"
    echo "  --erros          Mostra apenas linhas de ERRO e WARNING"
    echo "  --busca TEXTO    Filtra logs que contenham TEXTO"
    echo "  --hoje           Mostra apenas os logs de hoje"
    echo "  --help           Mostra esta ajuda"
    echo ""
    echo -e "${CYAN}Exemplos:${NC}"
    echo "  ./monitor_rp4.sh                # Acompanhar em tempo real"
    echo "  ./monitor_rp4.sh --erros        # Ver apenas erros"
    echo "  ./monitor_rp4.sh --busca 'HTTP' # Filtrar por texto"
    echo "  ./monitor_rp4.sh --status       # Ver se está rodando"
    echo ""
    echo -e "${YELLOW}Pressione CTRL+C para parar o monitoramento.${NC}"
}

case "${1:-}" in

    --help|-h)
        show_help
        ;;

    --journal|-j)
        echo -e "${GREEN}📡 Monitorando via journalctl (systemd)...${NC}"
        echo -e "${YELLOW}Pressione CTRL+C para sair.${NC}"
        echo ""
        journalctl -u telegram-bot.service -f --no-pager --output=short-iso
        ;;

    --full|-f)
        echo -e "${GREEN}📡 Monitorando journal + bot.log simultaneamente...${NC}"
        echo -e "${YELLOW}Pressione CTRL+C para sair.${NC}"
        echo ""
        # Usa journalctl em background e tail no foreground
        journalctl -u telegram-bot.service -f --no-pager --output=short-iso &
        JOURNAL_PID=$!
        trap "kill $JOURNAL_PID 2>/dev/null; exit 0" INT TERM
        if [ -f "$LOG_FILE" ]; then
            tail -f "$LOG_FILE"
        else
            echo "⚠️ Arquivo bot.log não encontrado. Mostrando apenas journal."
            wait $JOURNAL_PID
        fi
        ;;

    --status|-s)
        echo -e "${GREEN}=========================================="
        echo "   📊 Status do Bot"
        echo -e "==========================================${NC}"
        echo ""

        # Status do serviço
        echo -e "${CYAN}🔧 Serviço systemd:${NC}"
        systemctl status telegram-bot.service --no-pager 2>/dev/null || echo "  Serviço não encontrado."
        echo ""

        # PID Lock
        if [ -f /tmp/telegram-bot.pid ]; then
            PID=$(cat /tmp/telegram-bot.pid)
            if kill -0 "$PID" 2>/dev/null; then
                echo -e "${GREEN}🔒 Lock: Bot rodando (PID $PID)${NC}"
            else
                echo -e "${YELLOW}⚠️ Lock: PID $PID não existe (lock file residual)${NC}"
            fi
        else
            echo "🔓 Lock: Sem lock file (/tmp/telegram-bot.pid)"
        fi
        echo ""

        # Últimas linhas do log
        echo -e "${CYAN}📋 Últimas 30 linhas do bot.log:${NC}"
        echo "---"
        if [ -f "$LOG_FILE" ]; then
            tail -n 30 "$LOG_FILE"
        else
            echo "  (arquivo bot.log não encontrado)"
        fi
        ;;

    --erros|-e)
        echo -e "${GREEN}📡 Monitorando apenas ERROS e WARNINGS...${NC}"
        echo -e "${YELLOW}Pressione CTRL+C para sair.${NC}"
        echo ""
        if [ -f "$LOG_FILE" ]; then
            tail -f "$LOG_FILE" | grep --line-buffered -iE "(ERROR|WARNING|CRITICAL|Traceback|Exception)"
        else
            echo "⚠️ bot.log não encontrado. Usando journalctl..."
            journalctl -u telegram-bot.service -f --no-pager | grep --line-buffered -iE "(ERROR|WARNING|CRITICAL|Traceback|Exception)"
        fi
        ;;

    --busca|-b)
        if [ -z "${2:-}" ]; then
            echo "❌ Uso: ./monitor_rp4.sh --busca 'texto'"
            exit 1
        fi
        SEARCH_TERM="$2"
        echo -e "${GREEN}📡 Filtrando logs por: '${SEARCH_TERM}'${NC}"
        echo -e "${YELLOW}Pressione CTRL+C para sair.${NC}"
        echo ""
        if [ -f "$LOG_FILE" ]; then
            tail -f "$LOG_FILE" | grep --line-buffered -i "$SEARCH_TERM"
        else
            journalctl -u telegram-bot.service -f --no-pager | grep --line-buffered -i "$SEARCH_TERM"
        fi
        ;;

    --hoje|-t)
        echo -e "${GREEN}📡 Logs de hoje:${NC}"
        echo ""
        if [ -f "$LOG_FILE" ]; then
            TODAY=$(date +"%Y-%m-%d")
            grep "$TODAY" "$LOG_FILE" | tail -n 100
            echo ""
            echo -e "${CYAN}--- Mostrando últimas 100 linhas de hoje. Para tempo real use: ./monitor_rp4.sh${NC}"
        else
            journalctl -u telegram-bot.service --since today --no-pager
        fi
        ;;

    *)
        # Padrão: tail -f no bot.log
        echo -e "${GREEN}"
        echo "=========================================="
        echo "   📡 Monitor do Bot - Tempo Real"
        echo "=========================================="
        echo -e "${NC}"
        echo -e "${YELLOW}Pressione CTRL+C para sair.${NC}"
        echo ""

        if [ -f "$LOG_FILE" ]; then
            tail -f "$LOG_FILE"
        else
            echo "⚠️ bot.log não encontrado em $LOG_FILE"
            echo "Tentando via journalctl..."
            journalctl -u telegram-bot.service -f --no-pager --output=short-iso
        fi
        ;;
esac
