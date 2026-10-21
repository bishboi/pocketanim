from manim import *
from narrated import NarratedScene
from pathlib import Path
import numpy as np, json

A=Path(__file__).resolve().parent/'assets'
INK='#252623'; PAPER='#E3DDCB'; RED='#D94142'; YELLOW='#F4CE45'; OLIVE='#899565'; BLUE='#397D8C'; LAND='#D5C6A3'; WHITE='#F7F4E9'
DATA=json.loads((A/'maps.json').read_text())

def txt(s,size=30,color=INK,font=None):
    return Text(s,font=font or ('Kohinoor Devanagari' if any('\u0900'<=c<='\u097f' for c in s) else 'Avenir Next'),font_size=size,color=color)
def tag(s,p,size=26,fill=WHITE,color=INK):
    t=txt(s,size,color); b=Rectangle(width=t.width+.24,height=t.height+.18,stroke_color=INK,stroke_width=1.2,fill_color=fill,fill_opacity=1)
    return VGroup(b,t).move_to(p)
def label(s,p,size=30,color=INK): return txt(s,size,color).move_to(p)
def path(points,color=BLUE,width=4):
    v=VMobject().set_points_as_corners(points); v.set_stroke(color,width); return v
def mountain(p,s=.16):
    return Polygon(np.array(p)+[-s,-s*.65,0],np.array(p)+[0,s,0],np.array(p)+[s,-s*.65,0],stroke_color=INK,stroke_width=.8,fill_color=OLIVE,fill_opacity=1)
class Geo:
    def __init__(self,bounds,rect):
        self.lo,self.la,self.hi,self.ha=bounds; self.x,self.y,self.w,self.h=rect
    def p(self,lon,lat): return np.array([self.x+(lon-self.lo)/(self.hi-self.lo)*self.w,self.y+(lat-self.la)/(self.ha-self.la)*self.h,0])
    def country(self,n,fill=LAND,stroke=INK):
        return VGroup(*[Polygon(*[self.p(*c) for c in ring],stroke_color=stroke,stroke_width=.85,fill_color=fill,fill_opacity=1) for ring in DATA[n]])
    def region(self,pts,fill=RED): return Polygon(*[self.p(*p) for p in pts],stroke_color=RED,stroke_width=2,fill_color=fill,fill_opacity=.55)
    def river(self,pts): return path([self.p(*p) for p in pts],BLUE,4)

class Chapter(NarratedScene):
    def construct(self):
        self.bg=ImageMobject(str(A/'paper.png')).set(width=14.23,height=8)
        self.add(self.bg)
        self.folio=label('03   /   दो पड़ोसी, अलग जमीन',[-4.75,3.67,0],24)
        self.add(self.folio,Line([-6.6,3.35,0],[6.6,3.35,0],color=INK,stroke_width=1))
        self.base=list(self.mobjects)
        def at(t,*an,rt=.5):
            self.wait_until(t,lead=.15); self.play(*an,run_time=rt)
        def show(t,m,rt=.5): at(t,FadeIn(m,shift=UP*.08),rt=rt); return m
        def wipe(t):
            self.wait_until(t,lead=.15)
            obs=[m for m in self.mobjects if m not in self.base]
            if obs:self.play(*[FadeOut(m) for m in obs],run_time=.35)
        def head(s): return label(s,[0,2.8,0],43,font if False else INK)
        def caption(s,y=-3.25): return tag(s,[0,y,0],28,INK,WHITE)
        def leader(g,coord,s,pos,size=26,fill=WHITE):
            p=g.p(*coord); lab=tag(s,pos,size,fill); end=lab.get_left() if pos[0]>p[0] else lab.get_right()
            return VGroup(Line(p,end,color=INK,stroke_width=1.3),Dot(p,radius=.045,color=INK),lab)
        def china():
            g=Geo((73,18,136,54),(-6.3,-2.6,7.6,5.1));return g,g.country('China',WHITE)
        def japan():
            g=Geo((127,24,147,46),(-5.8,-2.7,6.2,5.7));return g,g.country('Japan',WHITE)
        # Opening: paired landforms
        c=Geo((73,18,136,54),(-5.9,-.5,5,2.9)).country('China',RED)
        j=Geo((127,24,147,46),(2,-.8,3.5,3.5)).country('Japan',RED)
        title=label('दो पड़ोसी, अलग जमीन',[0,-2.05,0],52)
        underline=Rectangle(width=9,height=.16,fill_color=YELLOW,fill_opacity=1,stroke_width=0).move_to([0,-2.55,0])
        show(.1,VGroup(c,j,title,underline),.7)
        show(3.6,VGroup(tag('CHINA',[-3.4,.6,0],30),tag('JAPAN',[4.7,1.45,0],30)))
        cues=VGroup(*[tag(s,[x,-3.1,0],27,fill) for s,x,fill in [('पहाड़',-4.65,OLIVE),('मैदान',-1.55,WHITE),('बारिश',1.55,WHITE),('समुद्र',4.65,'#A9C4C5')]])
        for t,o in zip([6.62,7.21,8.02,8.63],cues):show(t,o,.3)
        show(11.2,tag('नक्शा → जीवन',[0,1.15,0],34,YELLOW))
        # China land and rivers
        wipe(14.0); cg,cm=china();show(14.5,cm)
        show(15.6,VGroup(label('CHINA',[3.9,2.45,0],52),label('एक विशाल continental देश',[3.9,1.6,0],28)))
        climate=VGroup(*[tag(s,[3.9,y,0],27,co) for s,y,co in [('शुष्क उत्तर-पश्चिम',.6,LAND),('ठंडे ऊँचे पठार',-.15,OLIVE),('नम दक्षिण-पूर्व',-.9,'#B4C6B1')]])
        show(17.5,climate)
        peaks=VGroup(*[mountain(cg.p(x,y),.12) for x,y in [(81,35),(85,35),(89,34),(93,34),(97,33),(101,32),(87,39),(92,39),(97,38),(102,36),(105,30)]])
        show(19.8,peaks)
        at(21.1,FadeOut(climate))
        show(22.2,label('तीन बड़ी नदियाँ',[3.9,.85,0],34))
        rivers=[cg.river([(96,35),(101,36),(103,35),(104,37),(106,38),(107,40),(111,40),(111,35),(114,35),(117,37),(119,38)]),cg.river([(92,33),(96,33),(99,29),(101,26),(103,28),(106,29),(109,30),(112,30),(115,29),(118,31),(122,31)]),cg.river([(103,25),(106,24),(109,23),(111,23),(113.5,22.7)])]
        labs=[]
        for t,r,s,y in zip([24,26.1,28.1],rivers,['Huang He / Yellow River','Chang Jiang / Yangtse','Pearl River'],[.05,-.8,-1.65]):
            lab=label(s,[3.95,y,0],25,BLUE);labs.append(lab);at(t,Create(r),FadeIn(lab),rt=.6)
        show(31.2,tag('Yangtse  ·  दुनिया में तीसरी सबसे लंबी',[0,-3.3,0],29,YELLOW))
        at(33.3,*[FadeOut(m) for m in labs])
        show(35.2,label('अलग भूभाग\nअलग मौसम',[3.95,-.35,0],35))
        show(38.1,tag('एक जैसा जीवन नहीं',[3.95,-2.0,0],29,RED,WHITE))
        # people / languages
        wipe(40.2);cg,cm=china();cm.set_fill(LAND);show(40.35,cm)
        show(41.5,label('लोग और भाषाएँ',[3.9,2.5,0],40))
        show(42.15,tag('Han · सबसे बड़ा ethnic group',[2.9,1.45,0],27,YELLOW))
        show(44.0,label('Chinese / Putonghua',[3.3,.5,0],31))
        groups=VGroup(*[tag(s,[x,y,0],28) for s,x,y in [('Uighur',-4.6,1.2),('Hui',-2.6,.1),('Manchu',-.4,1.6),('Tibetan',-3.6,-1.6)]])
        for t,o in zip([46.6,47.48,47.9,48.82],groups):show(t,o,.3)
        show(50.0,caption('China ≠ एक ही तरह के लोग'))
        show(51.5,tag('Cantonese = Yue',[3.3,-.5,0],29))
        show(53.5,tag('Shanghainese = Wu',[3.3,-1.4,0],29))
        show(57.2,label('+ minority languages',[3.3,-2.35,0],28,RED))
        # food traditions
        wipe(63.5)
        show(63.8,label('विविधता थाली में भी',[0,2.65,0],45))
        foods=VGroup()
        for s,sub,p in [('उत्तर','wheat',[-3.65,1,0]),('पूर्व','rice + wheat',[3.65,1,0]),('दक्षिण','Cantonese',[-3.65,-1.2,0]),('Szechuan','तीखा cuisine',[3.65,-1.2,0])]:
            card=VGroup(Rectangle(width=5.5,height=1.65,stroke_color=INK,stroke_width=1,fill_color=WHITE,fill_opacity=.7).move_to(p),label(s,np.array(p)+[0,.33,0],34),label(sub,np.array(p)+[0,-.37,0],27));foods.add(card)
        show(66.3,foods,.6)
        show(70.7,SurroundingRectangle(foods[2],color=RED,buff=.07,stroke_width=4))
        show(72.6,caption('Canton → विदेशों में बसे Chinese समुदाय'))
        wipe(76.15)
        dim=ImageMobject(str(A/'dimsum.png')).set(height=5.65).move_to([-3.35,-.1,0]);show(76.5,dim)
        show(77.8,label('DIM SUM',[3.35,1.9,0],60))
        show(80.1,label('pastries + dumplings',[3.25,.8,0],30))
        show(83.4,tag('“आपके दिल को छूना”',[3.25,-.55,0],34,YELLOW))
        show(86.0,label('नाम भी, स्वाद भी।',[3.2,-1.8,0],30))
        # food geography and incoming ingredients
        wipe(87.95);cg,cm=china();show(88.15,cm)
        show(88.7,VGroup(tag('उत्तर',cg.p(110,42),29,YELLOW),label('WHEAT',[3.7,2.15,0],47)))
        show(91.2,VGroup(tag('पूर्व',cg.p(120,32),29,YELLOW),label('RICE + WHEAT',[3.7,1.25,0],35)))
        sz=Dot(cg.p(104,30.7),radius=.14,color=RED);sl=leader(cg,(104,30.7),'Szechuan',[-2.9,-2.2,0],28,YELLOW)
        show(95.3,VGroup(sz,sl,label('तीखा क्यों?',[3.7,-.1,0],40,RED)))
        show(100.1,tag('बाहर से आई सामग्री',[3.7,-1.25,0],28))
        at(102,FadeOut(sl))
        route=path([cg.p(76,40),cg.p(85,40),cg.p(94,36),cg.p(104,30.7)],OLIVE,5)
        show(102.8,tag('Buddhist monks',[-3.9,2.55,0],27,OLIVE))
        at(104,Create(route),rt=.8)
        show(104.7,tag('Silk Route · मसाले',[-3.7,1.65,0],27))
        sea=path([cg.p(126,21),cg.p(117,22),cg.p(111,25),cg.p(104,30.7)],RED,5)
        show(108.5,tag('Portuguese traders',[3.7,-2.2,0],27))
        at(109.6,Create(sea),rt=.75)
        show(110.0,caption('किताब के अनुसार: पंद्रहवीं सदी में मिर्च'))
        # Japan islands
        wipe(113.45);jg,jm=japan();show(114.2,jm)
        show(115.4,VGroup(label('JAPAN',[3.9,2.45,0],57),label('द्वीपों की लंबी श्रृंखला',[3.9,1.55,0],30)))
        jl=[]
        for t,coord,s,p in [(118.45,(142.3,43.4),'Hokkaido',[-1.0,2.8,0]),(120.51,(138,37),'Honshu',[-.1,.9,0]),(122.63,(133.6,33.6),'Shikoku',[-.1,-.6,0]),(123.61,(130.7,32.4),'Kyushu',[-5.35,-1.7,0])]:
            ob=leader(jg,coord,s,p,28);jl.append(ob);show(t,ob,.4)
        show(125.3,tag('चार सबसे बड़े द्वीप',[3.9,.45,0],29,YELLOW))
        ok=leader(jg,(127.7,26.3),'Okinawa',[-3.3,-3,0],27)
        show(128.4,ok)
        show(130.7,VGroup(label('Okinawa ≈ Bahamas',[3.9,-1.05,0],28),label('लगभग समान latitude',[3.9,-1.7,0],27),tag('करीब 26° N',[3.9,-2.5,0],29,'#B4C6B1')))
        # mountains architecture
        wipe(132.9);jg,jm=japan();show(133.1,jm)
        mt=VGroup(*[mountain(jg.p(x,y),.115) for x,y in [(142,44),(143,43),(141,42.7),(140.5,40.5),(140,39.6),(139.8,38.8),(139,38),(138,37),(137.5,36.2),(137,35.6),(136,35.1),(135,34.8),(133,34.5),(131,33),(130.6,32),(133.5,33.6)]])
        show(135.0,mt)
        stat=VGroup(label('50%+',[3.5,2.25,0],76),label('मुख्य द्वीपों की जमीन पहाड़ी',[3.5,1.35,0],28),Rectangle(width=4.8,height=.3,fill_color=WHITE,fill_opacity=1,stroke_color=INK).move_to([3.5,.7,0]),Rectangle(width=2.65,height=.3,fill_color=OLIVE,fill_opacity=1,stroke_width=0).move_to([2.425,.7,0]))
        show(134.3,stat)
        quake=tag('ACTIVE EARTHQUAKE ZONE',[3.5,-.35,0],26,RED,WHITE);show(137.1,quake)
        rings=VGroup(*[Circle(radius=r,color=RED,stroke_width=2).move_to(jg.p(138,36)) for r in [.28,.48,.7]])
        show(138,rings)
        at(140,FadeOut(stat))
        # simple architectural drawing
        house=VGroup(Rectangle(width=2.5,height=1.7,stroke_color=INK,fill_color=WHITE,fill_opacity=1).move_to([3.5,1.45,0]),Polygon([1.95,2.3,0],[3.5,3.1,0],[5.05,2.3,0],fill_color=RED,fill_opacity=1,stroke_color=INK),Rectangle(width=.5,height=1,fill_color=BLUE,fill_opacity=1,stroke_color=INK).move_to([3.5,1.1,0]),Line([1.6,.55,0],[5.4,.55,0],color=INK))
        show(142.3,house)
        show(143.5,label('खतरे को भूल सकते हैं?',[3.5,-1.25,0],30))
        show(145.8,tag('बिल्कुल नहीं',[3.5,-2.05,0],32,YELLOW))
        show(149.7,caption('GEOGRAPHY → ARCHITECTURE'))
        # population and colonial movement
        wipe(151.55);jg,jm=japan();show(151.8,jm)
        show(152.6,VGroup(label('लोग और पहचान',[3.6,2.65,0],40),tag('मुख्यतः Japanese',[3.6,1.65,0],32,YELLOW)))
        ain=leader(jg,(142,43),'Ainu · छोटी minority',[-1.35,2.8,0],27,YELLOW);show(153.95,ain)
        # Korea locator, to west of Japan in same projection
        kr=VGroup(jg.country('South Korea',LAND),jg.country('North Korea',LAND));show(156.1,kr)
        show(157.0,tag('Korean समुदाय',[3.6,.6,0],31))
        arrow=Arrow(jg.p(128,36),jg.p(133,34.5),color=RED,buff=.05,stroke_width=5)
        show(160.4,label('मजदूरों के परिवार भी',[3.6,-.4,0],29))
        show(163.0,tag('Japanese colonial rule',[3.6,-1.45,0],27))
        at(164.8,GrowArrow(arrow),FadeIn(caption('जबरन लाए गए मजदूर · अपनी पसंद से नहीं')),rt=.65)
        # Japan food
        wipe(166.3)
        show(166.7,label('Japan की थाली',[0,2.65,0],46))
        show(167.5,tag('Animal rearing की मजबूत परंपरा नहीं',[0,1.65,0],30))
        plate=ImageMobject(str(A/'japan_food.png')).set(height=5.0).move_to([3.45,-1.0,0]);show(169.8,plate)
        show(169.8,VGroup(label('RICE',[-3.6,.4,0],59),label('मुख्य फसल',[-3.6,-.3,0],30)))
        show(172.9,VGroup(label('FISH',[-3.6,-1.4,0],59),label('protein का बड़ा स्रोत',[-3.6,-2.15,0],30)))
        show(175.1,tag('Sashimi',[2.05,-3.15,0],29,YELLOW))
        show(176.05,tag('Sushi',[4.85,-3.15,0],29,YELLOW))
        show(179.0,tag('दुनिया भर में लोकप्रिय',[3.45,1.25,0],28))
        # Historical map
        wipe(181.0)
        eg=Geo((102,18,150,53),(-6.25,-2.95,9.1,5.95))
        east=VGroup(*[eg.country(n,WHITE) for n in ['China','Russia','Mongolia','North Korea','South Korea','Japan','Taiwan']])
        # crop China and Russia manually with shapely to avoid map offscreen
        from shapely.geometry import Polygon as SP, box
        def clipped_map(g,n,fill=WHITE):
            out=VGroup()
            for ring in DATA[n]:
                z=SP(ring).intersection(box(g.lo,g.la,g.hi,g.ha))
                if z.is_empty:continue
                zz=list(z.geoms) if hasattr(z,'geoms') else [z]
                for q in zz:
                    if q.geom_type=='Polygon' and q.area>.03:out.add(Polygon(*[g.p(*p) for p in q.exterior.coords],fill_color=fill,fill_opacity=1,stroke_color=INK,stroke_width=.8))
            return out
        east=VGroup(*[clipped_map(eg,n) for n in ['China','Russia','Mongolia','North Korea','South Korea','Japan','Taiwan']]);show(181.8,east)
        show(182.8,label('लाल सीमा',[4.7,2.45,0],37,RED))
        # Historical territorial extent, schematic mainland zones
        man=eg.region([(119,40),(122,40),(125,40),(129,43),(134,48),(131,49),(126,49),(120,46),(116,44)])
        coast=eg.region([(116,40),(120,40),(121,37),(120,34),(121.5,31),(121,28),(119,27),(118,29),(116,30),(114,30),(113,33),(114,36)])
        jap=eg.country('Japan','#E79B8A');kor=VGroup(eg.country('North Korea','#E79B8A'),eg.country('South Korea','#E79B8A'));tw=eg.country('Taiwan','#E79B8A')
        border=path([eg.p(*p) for p in [(145,47),(141,46),(137,40),(132,37),(130,31),(127,27),(124,23),(122,21),(119,22),(117,27),(112,30),(112,36),(115,41),(116,45),(120,47),(127,50),(134,49),(145,47)]],RED,2.7)
        show(183.2,border)
        date=label('1941',[4.7,1.35,0],75,RED);show(184.6,date)
        show(186.6,label('Japanese\nterritories',[4.7,.0,0],32))
        show(188.7,VGroup(tag('19वीं सदी की',[4.7,-1.35,0],28),tag('शुरुआत नहीं',[4.7,-2.05,0],28,YELLOW)))
        show(191.3,jap,.3);show(192.1,kor,.3);show(193.0,man,.35);show(194.1,coast,.4)
        show(195.1,caption('लाल: विस्तार / कब्ज़े का सांकेतिक क्षेत्र',-3.55))
        show(197.7,VGroup(tw,leader(eg,(121,23.7),'Taiwan',[-.4,-2.75,0],26)))
        city=[]
        for t,co,s,pos in [(199.5,(139.7,35.7),'Tokyo',[2.6,.75,0]),(200.4,(135.77,35.0),'Kyoto',[1.7,2.15,0]),(201.4,(132.45,34.4),'Hiroshima',[-1.0,.9,0]),(202.3,(129.87,32.75),'Nagasaki',[-1.5,-.55,0]),(203.7,(121.47,31.23),'Shanghai',[-4.8,-1.3,0])]:
            ob=leader(eg,co,s,pos,25);city.append(ob);show(t,ob,.3)
        # Seas: clear dense city labels and historical overlays
        at(205.3,*[FadeOut(m) for m in city],FadeOut(date),FadeOut(border),FadeOut(man),FadeOut(coast),FadeOut(jap),FadeOut(kor),FadeOut(tw))
        # clear right sidebar and all remaining historical labels; retain geographic map
        self.wait_until(205.9)
        extra=[m for m in self.mobjects if m not in self.base and m is not east]
        self.play(*[FadeOut(m) for m in extra],run_time=.3)
        show(206.6,label('PACIFIC\nOCEAN',[4.55,.6,0],38,BLUE))
        show(208.2,tag('Sea of Japan / East Sea',[-.3,2.6,0],26,'#C1D2CD'))
        show(210.5,tag('Yellow Sea',[-2.8,.5,0],26,'#C1D2CD'))
        show(211.5,tag('East China Sea',[-.5,-1.55,0],26,'#C1D2CD'))
        show(214.3,caption('समुद्र: अलगाव भी, व्यापार का रास्ता भी',-3.55))
        routes=VGroup(Arrow(eg.p(122,31),eg.p(131,33),buff=.1,color=BLUE,stroke_width=4),Arrow(eg.p(141,35),[5.9,-1.2,0],buff=.1,color=BLUE,stroke_width=4))
        at(216.0,*[GrowArrow(a) for a in routes],rt=.65)
        # wider Asia locator
        wipe(217.55)
        wg=Geo((65,8,151,59),(-6.4,-2.9,12.8,5.8))
        wide=VGroup(*[clipped_map(wg,n,RED if n=='Japan' else LAND) for n in ['China','Russia','Mongolia','Kazakhstan','India','North Korea','South Korea','Japan','Taiwan','Vietnam','Myanmar','Nepal','Bhutan','Bangladesh','Laos','Thailand','Pakistan','Afghanistan','Kyrgyzstan','Tajikistan']]);show(217.8,wide)
        for t,s,co in [(218.25,'Russia',(108,55)),(218.99,'Mongolia',(103,46)),(220.09,'Kazakhstan',(74,48)),(223.61,'India',(79,23))]:show(t,tag(s,wg.p(*co),28,YELLOW),.35)
        show(221.3,tag('JAPAN',wg.p(142,33),28,RED,WHITE))
        # closing question
        wipe(225.1)
        jg,jm=japan();jm.set_fill(RED);show(225.4,jm)
        show(226.5,label('जगह समझ आ गई।',[3.5,1.75,0],36))
        show(227.5,VGroup(label('असल सत्ता',[3.5,.45,0],49),tag('किसके पास थी?',[3.5,-.75,0],39,YELLOW)))
        self.wait_until_end()
