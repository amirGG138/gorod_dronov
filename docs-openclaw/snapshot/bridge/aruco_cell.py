"""cv2 ArUco cell localiser — independent reality-check of a drone's position.

Detects the DICT_4X4_1000 marker nearest the frame centre and maps it to a field
cell via the sverk aruco markers.txt. Used as extra positioning info (the ROS2
aruco->EKF flight path can be unstable, so we cross-check where the drone REALLY
is from what its camera sees). Two modes:

    python3 aruco_cell.py <image.png>     # one-shot, prints one JSON line
    python3 aruco_cell.py --service       # persistent: read image paths on
                                          # stdin, print one JSON line each
                                          # (imports cv2 + the map ONCE => fast)

Run with PYTHONPATH=/tmp/cvlib (isolated numpy<2 + opencv).
"""
import sys, json, math
import numpy as np, cv2, cv2.aruco as aruco

CELL = float(__import__("os").environ.get("CELL_SIZE", "0.6"))
ORIGIN = float(__import__("os").environ.get("FIELD_ORIGIN", "-1.5"))
MK = __import__("os").environ.get(
    "ARUCO_MARKERS",
    "/home/sverk/sverk_ws/src/sverk_drone/odometry/aruco/aruco_map/config/markers.txt")


def id2cell():
    m = {}
    for ln in open(MK):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        p = ln.split()
        if len(p) < 4:
            continue
        m[int(p[0])] = [int(round((float(p[2]) - ORIGIN) / CELL)),
                        int(round((float(p[3]) - ORIGIN) / CELL))]
    return m


def _detector():
    d = aruco.getPredefinedDictionary(aruco.DICT_4X4_1000)
    try:
        det = aruco.ArucoDetector(d, aruco.DetectorParameters())
        return lambda g: det.detectMarkers(g)[:2]
    except AttributeError:
        return lambda g: aruco.detectMarkers(g, d)[:2]


def detect(path, ID, det):
    img = cv2.imread(path)
    if img is None:
        return {"cell": None, "n": 0, "on_field": False, "err": "no img"}
    h, w = img.shape[:2]
    corners, ids = det(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    if ids is None or len(ids) == 0:
        return {"cell": None, "n": 0, "on_field": False}
    best, bestd = None, 1e9
    for c, i in zip(corners, ids.flatten()):
        pts = c.reshape(-1, 2)
        dist = math.hypot(pts[:, 0].mean() - w / 2, pts[:, 1].mean() - h / 2)
        if int(i) in ID and dist < bestd:
            bestd, best = dist, int(i)
    return {"cell": ID.get(best), "n": int(len(ids)), "on_field": True,
            "center_marker": best, "center_off_px": round(bestd, 1), "frame_w": w}


def main():
    ID = id2cell()
    det = _detector()
    if len(sys.argv) > 1 and sys.argv[1] == "--service":
        sys.stdout.write("READY\n"); sys.stdout.flush()
        for line in sys.stdin:
            path = line.strip()
            if not path:
                continue
            try:
                out = detect(path, ID, det)
            except Exception as e:
                out = {"cell": None, "on_field": False, "err": type(e).__name__}
            sys.stdout.write(json.dumps(out) + "\n"); sys.stdout.flush()
    elif len(sys.argv) > 1:
        print(json.dumps(detect(sys.argv[1], ID, det)))


if __name__ == "__main__":
    main()
