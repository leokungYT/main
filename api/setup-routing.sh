#!/system/bin/sh
# setup-routing.sh - run AS ROOT on emu via: su -c 'sh /data/local/tmp/setup-routing.sh'
# idempotent: safe to run many times

set -e

HOSTS=/system/etc/hosts
TMP=/data/local/tmp/hosts
LINE="127.0.0.1 rangers-api.line-apps.com"

# 1) hosts override via bind mount (idempotent)
if ! grep -q "rangers-api.line-apps.com" "$HOSTS" 2>/dev/null; then
    cp "$HOSTS" "$TMP"
    echo "$LINE" >> "$TMP"
    # umount if already bound (for clean re-apply), ignore error
    umount "$HOSTS" 2>/dev/null || true
    mount --bind "$TMP" "$HOSTS"
    echo "[+] hosts bind-mounted"
else
    echo "[=] hosts already has rangers-api"
fi

# 2) iptables REDIRECT 443 -> 8443 (idempotent: delete existing then add)
iptables -t nat -D OUTPUT -p tcp -d 127.0.0.1 --dport 443 -j REDIRECT --to-ports 8443 2>/dev/null || true
iptables -t nat -A OUTPUT -p tcp -d 127.0.0.1 --dport 443 -j REDIRECT --to-ports 8443
echo "[+] iptables REDIRECT 443->8443 applied"

# 3) verify
echo "--- hosts line ---"
grep rangers-api "$HOSTS" || echo "(none)"
echo "--- nat OUTPUT chain ---"
iptables -t nat -L OUTPUT -n | grep 8443 || echo "(none)"
echo "--- resolve rangers-api ---"
getent hosts rangers-api.line-apps.com 2>/dev/null || nslookup rangers-api.line-apps.com 2>/dev/null | head -5

echo "[+] routing setup complete"
