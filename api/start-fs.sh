#!/system/bin/sh
# จะถูก push ไป /data/local/tmp/ แล้ว chmod +x
# รัน fs เป็น daemon background จริงๆ
pkill -9 fs 2>/dev/null
pkill -9 frida-server 2>/dev/null
nohup /data/local/tmp/fs -l 0.0.0.0:27043 > /data/local/tmp/fs.log 2>&1 &
echo "started fs pid=$!"
sleep 1
ps -A | grep -E '/fs|frida'
