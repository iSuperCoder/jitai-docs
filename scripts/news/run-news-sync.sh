#!/usr/bin/env bash
# 服务器定时入口：只运行轻量 Python 生成器，不执行 Docusaurus、pnpm 或依赖安装。
# 默认只 build 候选；未来明确设置 NEWS_ENABLE_PUBLISH=1 后才允许自动发布。
# 凭证由进程环境提供，此脚本不 source 仓库文件、不打印环境、不启用 set -x。
set -euo pipefail

# 空值或仅空白视为尚未启用；先于 Python、锁、构建、发布和 CDN 重试退出，不产生数据文件。
feed_url="${NEWS_FEED_URL:-}"
if [[ -z "${feed_url//[[:space:]]/}" ]]; then
  printf '%s\n' '{"skipped":true,"reason":"feed_not_configured","changed":false}'
  exit 0
fi

# 固定为实际版本目录，发布时即使 /opt/jitai-news 链接切换，本次 build/publish 也使用同一版本。
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
NEWS_PYTHON="${NEWS_PYTHON:-python3}"
result="$("$NEWS_PYTHON" "$SCRIPT_DIR/sync_news.py" build)"
printf '%s\n' "$result"

if [[ "${NEWS_ENABLE_PUBLISH:-0}" == "1" ]]; then
  # 解析仅含摘要的 JSON，避免使用 eval 执行来源返回的数据。
  version="$(printf '%s' "$result" | "$NEWS_PYTHON" -c 'import json,sys; data=json.load(sys.stdin); print(data["version"] if data["changed"] else "")')"
  if [[ -n "$version" ]]; then
    "$NEWS_PYTHON" "$SCRIPT_DIR/sync_news.py" publish --version "$version"
  else
    # 源内容未变也可能还有上次失败的 CDN 任务，必须单独重试，不能假报发布完全成功。
    "$NEWS_PYTHON" "$SCRIPT_DIR/sync_news.py" retry-cdn
  fi
fi
