#!/bin/sh

export LC_ALL=en_US.utf-8
export LANG=en_US.utf-8
export FLASK_ENV=sandbox

PROJECT_DIR="/var/www/sandbox/WhatsApp-Backend"
LOG="$PROJECT_DIR/whatsapp_development.log"
pid_file="$PROJECT_DIR/app.pid"
PROJECT_NAME="WHATSAPP API BACKEND"

case $1 in
start)
  cd "$PROJECT_DIR"
  source venv/bin/activate
  echo "Starting $PROJECT_NAME"
  /opt/python/py3/bin/python /opt/python/py3/bin/flask run -h 0.0.0.0 -p 8888 &
  netstat -tulpn | grep 8888 | awk '{print $NF}' | awk -F '/' '{print $1}' > $pid_file
  pid=$(cat $pid_file)
  echo -n "Started $PROJECT_NAME WITH PID: $pid on port: $PORT"
  tail -f $LOG
  ;;
stop)
  echo "Stopping $PROJECT_NAME"
  kill -9 $(cat $pid_file)
  echo "Stopped $PROJECT_NAME: $(cat $pid_file)"
  ;;
restart)
  echo "Stopping $PROJECT_NAME"
  kill -9 $(cat $pid_file)
  echo "Stopped $PROJECT_NAME: $(cat $pid_file)"

  echo "Starting $PROJECT_NAME"
  cd "$PROJECT_DIR"
  /opt/python/py3/bin/python /opt/python/py3/bin/flask run -h 0.0.0.0 -p 8888 &
  netstat -tulpn | grep 8888 | awk '{print $NF}' | awk -F '/' '{print $1}' > $pid_file
  pid=$(cat $pid_file)
  echo -n "Started $PROJECT_NAME WITH PID: $pid on port: $PORT"
  echo
  tail-f $LOG
  ;;
*)
  echo "Usage: $0 {start|stop|restart}"
  exit 1
  ;;
esac


