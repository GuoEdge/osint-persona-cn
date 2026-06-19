#!/usr/bin/env bash
# Launch local OSINT Web UI (Linux / macOS)
set -euo pipefail

PORT="${PORT:-8787}"
HOST="${HOST:-127.0.0.1}"
NO_BROWSER="${NO_BROWSER:-0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="http://${HOST}:${PORT}"

banner() {
  echo ""
  echo "  OSINT 个人情报台"
  echo "  ${URL}"
  echo ""
}

get_python() {
  if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    echo "${ROOT}/.venv/bin/python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import sys; sys.exit(0 if sys.version_info < (3, 14) else 1)" 2>/dev/null || {
      echo "检测到 Python 3.14+，请使用项目 .venv 或 Python 3.12" >&2
      exit 1
    }
    command -v python3
    return
  fi
  echo "未找到 Python。请在项目目录创建 .venv: python3 -m venv .venv" >&2
  exit 1
}

healthy() {
  curl -fsS --max-time 3 "${URL}/api/extension/status" >/dev/null 2>&1
}

banner

if healthy; then
  echo "服务已在运行."
  [[ "${NO_BROWSER}" == "1" ]] || {
    if command -v xdg-open >/dev/null 2>&1; then xdg-open "${URL}" >/dev/null 2>&1 &
    elif command -v open >/dev/null 2>&1; then open "${URL}" >/dev/null 2>&1 &
    fi
  }
  exit 0
fi

PYTHON="$(get_python)"
export PYTHONPATH="${ROOT}/src"
cd "${ROOT}"

PY_VER="$("${PYTHON}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
echo "Python: ${PYTHON} (${PY_VER})"
if ! "${PYTHON}" -c "import rookiepy" 2>/dev/null; then
  echo "警告: 当前 Python 未安装 rookiepy，Cookie 同步可能失败。请 pip install -e \".[dev,web,bilibili]\""
fi
echo "正在启动... (Ctrl+C 停止服务)"
echo ""

if [[ "${NO_BROWSER}" != "1" ]]; then
  ( sleep 2; {
    if command -v xdg-open >/dev/null 2>&1; then xdg-open "${URL}" >/dev/null 2>&1
    elif command -v open >/dev/null 2>&1; then open "${URL}" >/dev/null 2>&1
    fi
  } ) &
fi

exec "${PYTHON}" -m osint_toolkit.cli web --host "${HOST}" --port "${PORT}"
