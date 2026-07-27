import os, time, json, urllib.request
os.environ["GZ_PARTITION"]="d0"; os.environ["GZ_WORLD"]="obrik_aruco6x6"
os.environ["CELL_SIZE_X"]="0.6"; os.environ["CELL_SIZE_Y"]="0.6"
os.environ["FIELD_ORIGIN_X"]="-1.5"; os.environ["FIELD_ORIGIN_Y"]="-1.5"
os.environ["DRONE_Z"]="1.5"
import sim_driver as sd
RGB={"drone-2":(0.25,0.73,0.31),"drone-3":(0.89,0.70,0.25),"drone-4":(0.97,0.47,0.73)}
PORT={"drone-2":9002,"drone-3":9003,"drone-4":9004}
for name,rgb in RGB.items():
    sd.remove_model(name)
    p=f"/tmp/{name}.sdf"; open(p,"w").write(sd.drone_sdf(name,rgb,0.0,0.0,1.5))
    sd.create_from_file(p,name)
print("spawned mirror cubes", flush=True)
def cell(port):
    try: return json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/pose",timeout=2)).get("xy")
    except Exception: return None
while True:
    for name,port in PORT.items():
        c=cell(port)
        if c: x,y=sd.cell_to_m(int(c[0]),int(c[1])); sd.set_pose(name,x,y,1.5)
    time.sleep(0.8)
