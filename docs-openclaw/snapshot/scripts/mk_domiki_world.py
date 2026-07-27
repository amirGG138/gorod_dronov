W="/home/sverk/PX4-Autopilot/Tools/simulation/gz/worlds"
sdf=open(W+"/obrik_aruco6x6.sdf").read()
sdf=sdf.replace('<world name="obrik_aruco6x6">','<world name="domiki6x6">')
inc=('    <include>\n'
     '      <uri>model://domiki_city</uri>\n'
     '      <pose>0 0 0.02 0 0 0</pose>\n'
     '    </include>\n  </world>')
sdf=sdf.replace('  </world>',inc,1)
open(W+"/domiki6x6.sdf","w").write(sdf)
print("wrote domiki6x6.sdf size",len(sdf),"| domiki refs",sdf.count("domiki_city"))
