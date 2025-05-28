#!/bin/bash

echo "🟢 Service-Status:"
echo "------------------"
for service in novnc x11vnc xvnc_session1; do
  echo "→ $service.service:"
  systemctl --no-pager status "$service.service" | grep -E 'Loaded|Active|Main PID' || echo "  [Service nicht gefunden]"
  echo ""
done

echo "🔌 Offene Ports (5900/5901 + 6080):"
echo "------------------"
ss -tlnp | grep -E ':(5900|5901|6080)' || echo "  [Keine relevanten Ports offen]"

echo ""
echo "🌐 Verbindungstest (curl):"
echo "------------------"
for port in 6080; do
  echo -n "→ http://localhost:$port : "
  curl -s -o /dev/null -w "%{http_code}\\n" http://localhost:$port || echo "Fehler"
done

echo ""
echo "✅ Statusprüfung abgeschlossen."