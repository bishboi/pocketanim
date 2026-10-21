from pathlib import Path
import numpy as np,json
from PIL import Image,ImageFilter
from cartopy.io import shapereader
from shapely.geometry import box
rng=np.random.default_rng(12)
h,w=720,1280
n=rng.normal(0,1.9,(h,w))
low=Image.fromarray(np.uint8(rng.uniform(0,255,(90,160)))).resize((w,h),Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(14))
a=np.array(low)/255-.5
base=np.array([229,224,207])[None,None,:]+n[:,:,None]+a[:,:,None]*9
Image.fromarray(np.uint8(np.clip(base,0,255))).save('assets/paper.png')
p=shapereader.natural_earth(resolution='50m',category='cultural',name='admin_0_countries')
d={}
for r in shapereader.Reader(p).records():
 g=r.geometry.intersection(box(94,17,151,55)).simplify(.075,preserve_topology=True)
 if g.is_empty:continue
 geoms=list(g.geoms) if g.geom_type=='MultiPolygon' else [g]
 out=[]
 for v in geoms:
  if v.geom_type=='Polygon' and v.area>.035:out.append(list(v.exterior.coords))
 if out:d[r.attributes['ADMIN']]=out
Path('assets/map.json').write_text(json.dumps(d))
print(d.keys())
