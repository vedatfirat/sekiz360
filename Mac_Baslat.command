#!/bin/bash
set -e
cd "$(dirname "$0")"
echo '========================================'
echo ' Operasyon360 - Pano & Evrak'
echo '========================================'
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3 bulunamadı. python.org üzerinden Python 3.11+ kurun.'
  read -r -p 'Kapatmak için Enter...' _
  exit 1
fi
if [ ! -d '.venv' ]; then
  echo 'İlk kurulum: sanal ortam hazırlanıyor...'
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -q -r requirements.txt
if [ ! -f data/ILK_GIRIS_BILGILERI.txt ]; then
  echo 'İlk çalıştırmada yönetici şifresi oluşturulacak.'
fi
export HOST=127.0.0.1
export PORT=8765
.venv/bin/python app.py &
PID=$!
trap 'kill "$PID" 2>/dev/null || true' EXIT
sleep 2
echo ''
echo 'Sistem adresi: http://127.0.0.1:8765'
echo ''
if [ -f data/ILK_GIRIS_BILGILERI.txt ]; then
  echo 'İlk giriş bilgileri (yalnızca ilk kurulumda kullanın):'
  cat data/ILK_GIRIS_BILGILERI.txt
fi
if command -v open >/dev/null 2>&1; then open 'http://127.0.0.1:8765'; fi
wait "$PID"
