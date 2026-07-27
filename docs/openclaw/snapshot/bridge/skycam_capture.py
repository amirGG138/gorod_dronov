import os, time, struct, zlib, threading
from gz.transport13 import Node
from gz.msgs10.image_pb2 import Image
# overview camera topic (env-configurable): default the domiki6x6 world skycam.
_W=os.environ.get("SKYCAM_WORLD","domiki6x6")
_M=os.environ.get("SKYCAM_MODEL","skycam_over")
TOPIC=os.environ.get("SKYCAM_TOPIC", f"/world/{_W}/model/{_M}/link/l/sensor/cam/image")
OUT=os.environ.get("OVERVIEW_DIR","/tmp/fleet/overview"); os.makedirs(OUT, exist_ok=True)
print(f"[skycam] topic {TOPIC} -> {OUT}", flush=True)
lock=threading.Lock(); state={"w":0,"h":0,"buf":None}
def png(path,w,h,data):
    raw=b"".join(b"\x00"+data[y*w*3:(y+1)*w*3] for y in range(h))
    def ch(t,d): return struct.pack(">I",len(d))+t+d+struct.pack(">I",zlib.crc32(t+d)&0xffffffff)
    open(path,"wb").write(b"\x89PNG\r\n\x1a\n"+ch(b"IHDR",struct.pack(">IIBBBBB",w,h,8,2,0,0,0))+ch(b"IDAT",zlib.compress(raw,6))+ch(b"IEND",b""))
def cb(m):
    with lock: state.update(w=m.width,h=m.height,buf=bytes(m.data))
n=Node(); n.subscribe(Image,TOPIC,cb)
print("skycam capture started",flush=True)
i=0
while True:
    time.sleep(4)
    with lock: w,h,buf=state["w"],state["h"],state["buf"]
    if buf and w:
        try:
            png(f"{OUT}/latest.png",w,h,buf[:w*h*3])
            png(f"{OUT}/frame_{i:04d}_{int(time.time())}.png",w,h,buf[:w*h*3]); i+=1
        except Exception as e: print("err",e,flush=True)
