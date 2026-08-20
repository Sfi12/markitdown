#!/bin/bash
# macOS Doppelklick-Starter: Bot + Dashboard
cd "$(dirname "$0")" || exit 1
export KEEP_OPEN=1
exec ./start_paper_trading.sh
