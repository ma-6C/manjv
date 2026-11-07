"""Deterministic 4x NSIS artwork. Never rasterize wizard labels or buttons."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from PIL import Image,ImageDraw

def generate():
    folder=ROOT/'assets/installer';folder.mkdir(parents=True,exist_ok=True)
    # NSIS's nominal welcome panel is 164x314 at 96 DPI. Four times that
    # resolution keeps geometric artwork sharp through common Windows scales.
    k=4;w,h=164*k,314*k
    im=Image.new('RGB',(w,h));px=im.load()
    for y in range(h):
        for x in range(w):
            t=.55*x/w+.45*y/h
            px[x,y]=(int(22+13*t),int(22+8*t),int(36+34*t))
    d=ImageDraw.Draw(im)
    def poly(points,color):d.polygon([(int(x*k),int(y*k)) for x,y in points],fill=color)
    # Original geometric ribbons echo an editor's vivid left-hand identity.
    poly([(-26,188),(137,29),(202,92),(39,251)],'#7048E8')
    poly([(-38,231),(171,41),(194,91),(-15,281)],'#A56AFF')
    poly([(-27,247),(144,91),(189,132),(18,288)],'#D878E8')
    poly([(-18,265),(164,106),(182,150),(0,309)],'#FF9D76')
    poly([(65,238),(191,126),(198,195),(103,279)],'#5B52D9')
    # Film-frame emblem: a scalable shape rather than a copied third-party logo.
    d.rounded_rectangle((26*k,40*k,112*k,126*k),radius=17*k,fill='#15151F',outline='#FFFFFF',width=2*k)
    d.polygon([(60*k,62*k),(60*k,103*k),(89*k,82*k)],fill='#FFFFFF')
    for x in (38,91):
        for y in (54,74,94,110):d.rounded_rectangle((x*k,y*k,(x+6)*k,(y+5)*k),radius=k,fill='#AC96F4')
    im.save(folder/'wizard.bmp')
    head=Image.new('RGB',(150*k,57*k),'white')
    icon=Image.open(ROOT/'assets/app.png').convert('RGBA').resize((36*k,36*k),Image.Resampling.LANCZOS)
    head.paste(icon,(102*k,10*k),icon);head.save(folder/'header.bmp')
    print('INSTALLER_ARTWORK_OK',im.size,head.size)

if __name__=='__main__':generate()
