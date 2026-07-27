#!/bin/bash
# Запуск hold_aruco на борту Обрика.
#
# Существует ровно из-за одной ловушки: на борту через pip поставлен numpy 2.2.6
# поверх системного 1.21.5, а python3-opencv (4.5.4) собран под первый. Без
# подмены приоритета `import cv2` падает с
#     ImportError: numpy.core.multiarray failed to import
# и это ломает не только нас — sverk_interfaces тоже импортирует cv2.
# /usr/lib/python3/dist-packages — это системные пакеты из apt, где лежит
# согласованная пара numpy 1.21.5 + cv2 4.5.4.
set -e

source /opt/ros/*/setup.bash
source ~/sverk_ws/install/setup.bash
export PYTHONPATH=/usr/lib/python3/dist-packages:$PYTHONPATH

exec python3 "$(dirname "$0")/hold_aruco.py" "$@"
