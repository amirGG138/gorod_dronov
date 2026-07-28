#!/usr/bin/env bash
# Запуск бортового агента на дроне. Кладётся рядом с drone_agent.py.
#
# Зачем скрипт: голый `python3 drone_agent.py` на борту не работает.
#   1. системный python3 не может импортировать cv2 — поверх numpy 1.21.5 доставлен
#      numpy 2.2.6, а python3-opencv 4.5.4 собран под 1.x. Обход — окружение ~/venv_fly.
#   2. sverk_interfaces виден только после source двух setup.bash (по ssh .bashrc не читается).
# Проверено на борту 192.168.1.105 2026-07-28.
#
#   ./run_agent.sh --name m1 --cell 1,1        # все аргументы уходят в drone_agent.py

set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="${VENV:-$HOME/venv_fly/bin/python}"
WS="${WS:-$HOME/sverk_ws/install/setup.bash}"
ROS="${ROS:-/opt/ros/humble/setup.bash}"

for f in "$VENV" "$WS" "$ROS"; do
    [ -e "$f" ] || { echo "нет файла: $f — проверьте окружение на борту" >&2; exit 1; }
done

# shellcheck disable=SC1090
set +u
. "$ROS"
. "$WS"
set -u

exec "$VENV" "$HERE/drone_agent.py" "$@"
