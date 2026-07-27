# Единая bridge-нода дрона поверх ВАШЕГО ROS2-образа (sverk-ros2).
#
# Базовый образ должен содержать rclpy + собранный sverk_ws (sverk_interfaces,
# led_control, offboard_control, ros2_mcp) — то, что собирает пайплайн репы
# sverk-ros2. Тег передаётся build-arg'ом:
#
#   docker build -f bridge/ros2/Dockerfile \
#     --build-arg SVERK_ROS2_IMAGE=<registry>/sverk-ros2:<tag> \
#     -t openclaw-bridge-ros2 .
#
# Запуск на дроне — docker-compose.drone.yml c BRIDGE_IMAGE=openclaw-bridge-ros2
# (сеть host, чтобы нода видела DDS/микроагент PX4 и ros2_mcp на :9092).
ARG SVERK_ROS2_IMAGE=sverk-ros2:latest
FROM ${SVERK_ROS2_IMAGE}

COPY bridge/ros2/bridge_node.py /app/bridge_node.py

ENV PORT=9000 \
    BRIDGE_MODE=city \
    BRIDGE_FRAME=aruco_map \
    CELL_SIZE_M=0.8 \
    FLIGHT_ALT_M=1.5 \
    ROS2_MCP_URL=http://localhost:9092

# ROS2-окружение поднимает entrypoint базового образа (source setup.bash);
# наша нода — просто python-процесс в нём.
CMD ["python3", "/app/bridge_node.py"]
