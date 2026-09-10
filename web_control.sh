#!/bin/bash

# ========================================
# Web服务控制脚本
# 用法: ./web_control.sh {start|stop|restart|status|logs}
# ========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# ====== 配置 ======
CONDA_ENV="bioagent"
LOG_FILE="$SCRIPT_DIR/web_service.log"
PID_FILE="$SCRIPT_DIR/web_service.pid"
HOST="0.0.0.0"
PORT="39006"
MODULE="interfaces.web"
STOP_TIMEOUT=10
# =================

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

pid_alive() {
    [[ "$1" =~ ^[0-9]+$ ]] && kill -0 "$1" 2>/dev/null
}

# 检查conda环境，并解析环境内的 python 路径
resolve_python() {
    local conda_base python_bin

    if ! command -v conda &> /dev/null; then
        print_error "conda命令不可用"
        return 1
    fi

    if ! conda env list | grep -qE "^${CONDA_ENV}[[:space:]]"; then
        print_error "conda环境 '$CONDA_ENV' 不存在"
        print_info "可用环境:"
        conda env list
        return 1
    fi

    conda_base="$(conda info --base 2>/dev/null)"
    python_bin="${conda_base}/envs/${CONDA_ENV}/bin/python"
    if [ ! -x "$python_bin" ]; then
        print_error "找不到解释器: $python_bin"
        return 1
    fi

    echo "$python_bin"
}

# 端口上的监听进程
pids_on_port() {
    local pids=""

    if command -v ss >/dev/null 2>&1; then
        pids="$(ss -lptn "sport = :${PORT}" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2)"
    fi
    if [ -z "$pids" ] && command -v lsof >/dev/null 2>&1; then
        pids="$(lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null)"
    fi
    if [ -z "$pids" ] && command -v fuser >/dev/null 2>&1; then
        pids="$(fuser "${PORT}/tcp" 2>/dev/null)"
    fi

    echo "$pids" | tr -s '[:space:]' '\n' | grep -E '^[0-9]+$' | sort -u
}

# 命令行匹配到的 Web 进程
pids_by_pattern() {
    pgrep -f "(python|python3).*-m[ ]*${MODULE}" 2>/dev/null | sort -u
}

# 汇总 PID：PID 文件 + 端口 + 命令行（解决 conda run 记错 PID 的问题）
collect_pids() {
    local pid
    local -a all=()

    if [ -f "$PID_FILE" ]; then
        pid="$(tr -d ' \t\r\n' < "$PID_FILE")"
        if pid_alive "$pid"; then
            all+=("$pid")
        fi
    fi

    local extra
    extra="$(pids_on_port; pids_by_pattern)"
    if [ -n "$extra" ]; then
        # shellcheck disable=SC2206
        all+=($extra)
    fi

    if [ "${#all[@]}" -eq 0 ]; then
        return 1
    fi
    printf '%s\n' "${all[@]}" | grep -E '^[0-9]+$' | sort -u
}

# 杀掉进程及其子进程（conda/nohup 包装层）
kill_tree() {
    local pid="$1"
    local sig="$2"
    local pgid child

    pid_alive "$pid" || return 0

    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
    if [[ "$pgid" =~ ^[0-9]+$ ]]; then
        kill "-$sig" -- "-$pgid" 2>/dev/null || true
    fi
    kill "-$sig" "$pid" 2>/dev/null || true

    for child in $(pgrep -P "$pid" 2>/dev/null); do
        kill "-$sig" "$child" 2>/dev/null || true
    done
}

# 检查服务状态
check_status() {
    local pids pid rss start cmd

    pids="$(collect_pids || true)"
    if [ -n "$pids" ]; then
        echo -e "${GREEN}● 服务正在运行${NC}"
        while read -r pid; do
            [ -n "$pid" ] || continue
            start="$(ps -p "$pid" -o lstart= 2>/dev/null)"
            rss="$(ps -p "$pid" -o rss= 2>/dev/null | awk '{printf "%.2f MB", $1/1024}')"
            cmd="$(ps -p "$pid" -o args= 2>/dev/null)"
            echo "  PID: $pid"
            echo "  启动时间: $start"
            echo "  内存使用: $rss"
            echo "  命令: $cmd"
        done <<< "$pids"
        echo "  监听地址: $HOST:$PORT"
        return 0
    fi

    if [ -f "$PID_FILE" ]; then
        rm -f "$PID_FILE"
        echo -e "${RED}● 服务未运行${NC}（已清理残留 PID 文件）"
    else
        echo -e "${RED}● 服务未运行${NC}"
    fi
    return 1
}

# 启动服务
start_service() {
    local python_bin pid i

    print_info "检查conda环境..."
    python_bin="$(resolve_python)" || return 1

    if pids="$(collect_pids)"; then
        print_warning "服务已经在运行中 (PID: $(echo "$pids" | tr '\n' ' '))"
        echo "如需重启，请执行: $0 restart"
        echo "$pids" | head -n 1 > "$PID_FILE"
        return 1
    fi

    print_info "启动Web服务..."
    print_info "Conda环境: $CONDA_ENV"
    print_info "解释器: $python_bin"
    print_info "监听地址: $HOST:$PORT"
    print_info "日志文件: $LOG_FILE"

    # 直接用环境内 python 启动，避免 conda run 包装进程导致 stop 杀错 PID
    setsid "$python_bin" -B -m "$MODULE" --host "$HOST" --port "$PORT" \
        >> "$LOG_FILE" 2>&1 < /dev/null &
    pid=$!
    echo "$pid" > "$PID_FILE"

    for ((i = 0; i < 16; i++)); do
        if ! pid_alive "$pid"; then
            print_error "服务启动失败，请检查日志: $LOG_FILE"
            rm -f "$PID_FILE"
            tail -n 30 "$LOG_FILE" 2>/dev/null || true
            return 1
        fi
        if [ -n "$(pids_on_port)" ]; then
            print_success "服务启动成功 (PID: $pid)"
            echo "========================================="
            echo "查看日志: tail -f $LOG_FILE"
            echo "查看状态: $0 status"
            echo "停止服务: $0 stop"
            echo "========================================="
            return 0
        fi
        sleep 0.5
    done

    if pid_alive "$pid"; then
        print_warning "进程已启动 (PID: $pid)，但端口 $PORT 尚未监听，请查看日志"
        return 0
    fi

    print_error "服务启动失败，请检查日志: $LOG_FILE"
    rm -f "$PID_FILE"
    return 1
}

# 停止服务
stop_service() {
    local pids pid leftover still

    pids="$(collect_pids || true)"
    if [ -z "$pids" ]; then
        print_warning "服务未运行"
        rm -f "$PID_FILE"
        return 0
    fi

    print_info "正在停止服务 (PID: $(echo "$pids" | tr '\n' ' '))..."

    while read -r pid; do
        [ -n "$pid" ] || continue
        kill_tree "$pid" TERM
    done <<< "$pids"

    for ((i = 0; i < STOP_TIMEOUT; i++)); do
        leftover="$(collect_pids || true)"
        [ -z "$leftover" ] && break
        sleep 1
    done

    leftover="$(collect_pids || true)"
    if [ -n "$leftover" ]; then
        print_warning "进程未响应，强制停止..."
        while read -r pid; do
            [ -n "$pid" ] || continue
            kill_tree "$pid" KILL
        done <<< "$leftover"
        sleep 1
    fi

    still="$(collect_pids || true)"
    rm -f "$PID_FILE"

    if [ -z "$still" ]; then
        print_success "服务已停止"
        return 0
    fi

    print_error "服务停止失败，残留 PID: $(echo "$still" | tr '\n' ' ')"
    return 1
}

# 重启服务
restart_service() {
    print_info "重启服务..."
    stop_service || true
    local i
    for ((i = 0; i < 20; i++)); do
        [ -z "$(pids_on_port)" ] && break
        sleep 0.3
    done
    start_service
}

# 查看日志
show_logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        print_error "日志文件不存在: $LOG_FILE"
        return 1
    fi
}

# 查看最近日志
show_last_logs() {
    if [ -f "$LOG_FILE" ]; then
        echo "最近50行日志:"
        echo "========================"
        tail -n 50 "$LOG_FILE"
    else
        print_error "日志文件不存在: $LOG_FILE"
        return 1
    fi
}

# 显示帮助
show_help() {
    cat << EOF
用法: $0 {start|stop|restart|status|logs|tail|help}

命令:
  start    启动服务
  stop     停止服务
  restart  重启服务
  status   查看服务状态
  logs     实时查看日志 (tail -f)
  tail     查看最近50行日志
  help     显示此帮助信息

示例:
  $0 start    # 启动服务
  $0 status   # 查看状态
  $0 logs     # 查看实时日志
  $0 stop     # 停止服务
  $0 restart  # 重启服务

配置:
  Conda环境: $CONDA_ENV
  监听地址:  $HOST:$PORT
  日志文件:  $LOG_FILE
  PID文件:   $PID_FILE

EOF
}

# ========================================
# 主程序
# ========================================

status=0
case "$1" in
    start)
        start_service || status=$?
        ;;
    stop)
        stop_service || status=$?
        ;;
    restart)
        restart_service || status=$?
        ;;
    status)
        check_status || status=$?
        ;;
    logs)
        show_logs || status=$?
        ;;
    tail)
        show_last_logs || status=$?
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        if [ -z "$1" ]; then
            echo "错误：缺少参数"
            echo ""
            show_help
            status=1
        else
            print_error "未知命令: $1"
            echo ""
            show_help
            status=1
        fi
        ;;
esac

exit "$status"
