import json, time, urllib.request


B = "http://192.168.1.125"
def get(url):
    try:
        return json.loads(urllib.request.urlopen(B + url, timeout=10).read())
    except Exception as exc:
        return {"error": str(exc)}

  # параметры самого скана
sc = get("/api/ros/topic?name=/scan&type=sensor_msgs/msg/LaserScan").get("latest_message") or {}
if sc:
    amin, amax, ainc = sc.get("angle_min"), sc.get("angle_max"), sc.get("angle_increment")
    print(f"скан: сектор {math.degrees(amin):.0f}..{math.degrees(amax):.0f}°, "
        f"шаг {math.degrees(ainc):.2f}°, лучей {len(sc.get('ranges') or [])}, "
        f"range {sc.get('range_min')}..{sc.get('range_max')} м")

for name, kind in (("/amcl_pose", "geometry_msgs/msg/PoseWithCovarianceStamped"),
                     ("/scan_filtered", "sensor_msgs/msg/LaserScan"),
                     ("/map", "nav_msgs/msg/OccupancyGrid")):
    get(f"/api/ros/topic?name={name}&type={kind}")
time.sleep(2.5)
for name, kind in (("/amcl_pose", "geometry_msgs/msg/PoseWithCovarianceStamped"),
                     ("/scan_filtered", "sensor_msgs/msg/LaserScan"),
                     ("/map", "nav_msgs/msg/OccupancyGrid")):
    d = get(f"/api/ros/topic?name={name}&type={kind}")
    print(f"  {name}: сообщений {d.get('message_count')}, возраст {d.get('age_sec')}, "
            f"издателей {d.get('publishers')}")


def call(service, kind, request=None, timeout=40):
    body = json.dumps({"service": service, "type": kind, "request": request or {}}).encode()
    r = urllib.request.Request("http://192.168.1.125/api/ros/service/call", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        return json.loads(urllib.request.urlopen(r, timeout=timeout).read())
    except Exception as exc:
         return {"error": str(exc)}

def state(node):
    a = call(f"{node}/get_state", "lifecycle_msgs/srv/GetState", timeout=15)
    return ((a.get("response") or {}).get("current_state") or {}).get("label", a.get("error", "?"))

# 1 = configure, 3 = activate (lifecycle_msgs/msg/Transition)
def activate(node):
    was = state(node)
    if was == "active":
        return print(f"  {node}: уже active")
    if was == "unconfigured":
        a = call(f"{node}/change_state", "lifecycle_msgs/srv/ChangeState",
                   {"transition": {"id": 1, "label": "configure"}})
        print(f"  {node}: configure -> {(a.get('response') or {}).get('success', a.get('error'))}")
        time.sleep(1.0)
    a = call(f"{node}/change_state", "lifecycle_msgs/srv/ChangeState",
               {"transition": {"id": 3, "label": "activate"}})
    ok = (a.get("response") or {}).get("success", a.get("error"))
    print(f"  {node}: {was} -> activate: {ok} -> {state(node)}")

for node in ("/global_costmap/global_costmap", "/planner_server", "/behavior_server",
               "/bt_navigator", "/waypoint_follower"):
    activate(node)
    time.sleep(0.5)

st = json.loads(urllib.request.urlopen("http://192.168.1.125:8767/v1/state", timeout=8).read())
print("\nnav2_ready:", st.get("nav2_ready"), "| фрейм позы:", (st.get("pose") or {}).get("frame_id"))


def call(service, kind, request=None, timeout=40):
    body = json.dumps({"service": service, "type": kind, "request": request or {}}).encode()
    r = urllib.request.Request("http://192.168.1.125/api/ros/service/call", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        return json.loads(urllib.request.urlopen(r, timeout=timeout).read())
    except Exception as exc:
        return {"error": str(exc)}

cov = [0.0] * 36
cov[0] = cov[7] = 0.25      # x, y
cov[35] = 0.0685            # yaw
req = {"pose": {"header": {"frame_id": "map"},
                  "pose": {"pose": {"position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}},
                           "covariance": cov}}}
print("set_initial_pose ->", call("/set_initial_pose", "nav2_msgs/srv/SetInitialPose", req))
time.sleep(3)

def state(node):
    a = call(f"{node}/get_state", "lifecycle_msgs/srv/GetState", timeout=15)
    return ((a.get("response") or {}).get("current_state") or {}).get("label", a.get("error", "?"))

for node in ("/global_costmap/global_costmap", "/planner_server"):
      a = call(f"{node}/change_state", "lifecycle_msgs/srv/ChangeState",
               {"transition": {"id": 3, "label": "activate"}}, timeout=50)
      print(f"  {node}: activate -> {(a.get('response') or {}).get('success', a.get('error'))} -> {state(node)}")
      time.sleep(1)

st = json.loads(urllib.request.urlopen("http://192.168.1.125:8767/v1/state", timeout=8).read())
print("\nnav2_ready:", st.get("nav2_ready"), "| поза:", st.get("pose"))


def call(service, kind, request=None, timeout=40):
    body = json.dumps({"service": service, "type": kind, "request": request or {}}).encode()
    r = urllib.request.Request("http://192.168.1.125/api/ros/service/call", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        return json.loads(urllib.request.urlopen(r, timeout=timeout).read())
    except Exception as exc:
          return {"error": str(exc)}

cov = [0.0] * 36
cov[0] = cov[7] = 0.25      # x, y
cov[35] = 0.0685            # yaw
req = {"pose": {"header": {"frame_id": "map"},
                  "pose": {"pose": {"position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}},
                           "covariance": cov}}}
print("set_initial_pose ->", call("/set_initial_pose", "nav2_msgs/srv/SetInitialPose", req))
time.sleep(3)

def state(node):
    a = call(f"{node}/get_state", "lifecycle_msgs/srv/GetState", timeout=15)
    return ((a.get("response") or {}).get("current_state") or {}).get("label", a.get("error", "?"))

for node in ("/global_costmap/global_costmap", "/planner_server"):
    a = call(f"{node}/change_state", "lifecycle_msgs/srv/ChangeState",
               {"transition": {"id": 3, "label": "activate"}}, timeout=50)
    print(f"  {node}: activate -> {(a.get('response') or {}).get('success', a.get('error'))} -> {state(node)}")
    time.sleep(1)

st = json.loads(urllib.request.urlopen("http://192.168.1.125:8767/v1/state", timeout=8).read())
print("\nnav2_ready:", st.get("nav2_ready"), "| поза:", st.get("pose"))


