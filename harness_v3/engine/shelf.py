"""The shelf's index: every drawn thing (props.py draws them) by its section, the words that call each section up,
the other names things go by, and what a shot is shown of it. Light (no drawing), so the prompts, the score reader
and the asset step can use it.

    shelf_for(text)     the things a shot is likely to need, by its plan and words: what it names, the sections its
                        words call up, and a few everyday things (the prompt is not given all of the shelf every shot)
    headings()          the sections and a few things in each (for the director, who plans shots, not lines)
    known(name)         the drawn thing a name is (its own name or another), or None
    stand_in(name, of)  a thing not on the shelf: the words its picture is made from instead (assets.py, look.py)
"""

from __future__ import annotations

import re

# Each section: the things in it. (A test keeps this and props.SHELF the same.)
SECTIONS = {
    "Money, trade": (
        "moneybag coins coin goldbars cash gem crown chest piggybank wallet card receipt abacus safe stall scales "
        "shoppingcart pricetag cashregister atm suitcase backpack scepter orb ring necklace"),
    "Writing, office": (
        "book books openbook ledger scroll letter document charter newspaper oldmap quill inkwell seal pencil "
        "notebook clipboard folder stamp typewriter briefcase ballotbox calendar ticket passport idcard cheque "
        "parcel"),
    "Modern": (
        "laptop computer phone oldphone radio tv camera microphone megaphone clock lightbulb battery robot drone "
        "calculator streetlight trafficlight printer router satellitedish cctv chip tablet mobiletower plug "
        "qrcode conveyor robotarm"),
    "Science, industry": (
        "flask testtube microscope magnet gear telescope rocket satellite solarpanel windmill factory oilwell "
        "printingpress dna deskglobe compass windturbine pylon oilbarrel fuelpump container crane atom molecule "
        "virus cell brain skull bone tooth prism planet earth comet bunsen sundial magnifier rover spacestation "
        "galaxy circuit oilrig coal furnace steamengine telegraph"),
    "Home": (
        "table desk chair stool throne bench bookshelf lectern bed charpai rug vase broom umbrella ladder rope "
        "chain padlock key bell goblet hourglass gift balloon kite ball cricketbat trophy medal lattu rangoli "
        "sofa tablelamp mirror door window stairs kettle pan plate bottle jug mailbox fan fridge shoe shirt "
        "whiteboard blackboard spectacles fireextinguisher clothesline cradle mat pillow iron sewingmachine "
        "washingmachine dustbin candle diya lantern campfire"),
    "Containers": (
        "barrel crate box sack basket pot jar bucket milkcan tiffin"),
    "Food": (
        "bread apple mango banana coconut wheat bowl thali teacup kulhad fish cake pizza egg carrot tomato onion "
        "chili grapes watermelon icecream samosa laddoo sugarcane teapot roti pressurecooker mortar gascylinder "
        "jalebi dosa idli noodles burger coffee orange lemon potato corn salt"),
    "Care, learning": (
        "medkit pills syringe mask thermometer heart gradcap diploma stethoscope bandage wheelchair crayons ruler "
        "slate ecg hospitalbed xray"),
    "Arms": (
        "sword shield spear bow axe musket cannon bomb helmet dagger mace armor arrow quiver catapult cannonballs "
        "chariot tank banner drum horn crossbow torch trench barbedwire mushroomcloud"),
    "Tools": (
        "anvil plough wheel charkha hammer saw wrench screwdriver shovel pickaxe sickle hoe pitchfork wateringcan "
        "wheelbarrow toolbox scissors paintbrush easel"),
    "Music, play, sport": (
        "guitar piano harmonium dhol violin headphones speaker dice chessboard playingcards gamecontroller racket "
        "dumbbell hockeystick"),
    "Law": (
        "gavel handcuffs evm stopsign podium placard inkedfinger constitution"),
    "Getting about": (
        "cart carriage bicycle rickshaw autorickshaw car bus truck tractor train plane boat ship motorcycle "
        "scooter helicopter hotairballoon submarine sailboat canoe ambulance firetruck policecar jeep bulldozer "
        "jet tram trafficcone railtrack station busstop milestone"),
    "Places": (
        "house hut tent well tower castle palace temple mosque church school hospital bank shop skyscraper "
        "lighthouse bridge gate fence signpost flagpole flagindia bunting pyramids obelisk pillar arch statue "
        "fountain stupa parliament court prison dam barn silo warehouse igloo pagoda tajmahal indiagate "
        "eiffeltower colosseum greatwall powerplant"),
    "Land and water": (
        "river lake waterfall hills mountainrange snowpeak valley desert dune oasis forest jungle swamp glacier "
        "iceberg canyon cliff cave beach ocean coast delta plateau meadow acacia bamboo banyan terraces mangrove "
        "reef geyser crater road trail village skyline port mine quarry sunset nightsky"),
    "Nature": (
        "tree palm bush rock mountain cloud sun moon flower lotus cactus mushroom pinetree wave raincloud "
        "lightning snowflake star rainbow volcano island leaf sprout beehive nest logs haystack scarecrow tornado"),
    "Environment, water, power": (
        "recycle watertank tap pipe garbage smog chargingstation"),
    "India": (
        "loom kalash conch sitar tabla flute palanquin chulha handpump spices puppet jalebi dosa idli"),
    "First farmers, first cities": (
        "kernel handaxe flintknife polishedaxe cavepainting leanto quern barley millet riceplant lentils peapod "
        "cotton flax yarn spindle clothbolt storagejar copperore ingot obsidian seashell lapis claytablet stylus "
        "claylump ziggurat mudbricks citywall stele cylinderseal claycones potterswheel lyre dates barge shaduf "
        "canal cheese hide oillamp sealing beacon tabletshelf eclipse mudhouse field yoke fishingnet"),
}

# The words in a shot's plan or narration that call a section up.
KEYWORDS = {
    "Money, trade": (
        "money coin coins cash rupee rupees dollar gold silver trade trader market buy sell sold bought price "
        "prices tax taxes bank wealth rich poor debt loan pay paid wage wages salary profit shop shopping "
        "merchant economy treasure jewel king queen royal"),
    "Writing, office": (
        "write writing wrote written book books letter letters paper document documents record records law laws "
        "treaty charter newspaper news map maps office clerk read reading print printed ink library archive vote "
        "election ballot"),
    "Modern": (
        "phone mobile computer laptop internet digital radio television tv camera robot drone technology tech app "
        "online modern today factory automation payment"),
    "Science, industry": (
        "science scientist experiment lab laboratory chemistry physics biology space planet star stars rocket "
        "satellite moon industry industrial machine machines engine steam coal oil energy electricity power "
        "invention invented gear factory mine metal dna gene atom virus disease telescope"),
    "Home": (
        "home house family household kitchen room bed chair table sofa wash washing clothes cook cooking child "
        "children baby mother father sleep"),
    "Containers": (
        "store stored storage grain carry jar pot barrel box sack basket bucket"),
    "Food": (
        "food eat eating ate meal meals bread rice wheat fruit vegetable vegetables cook cooking hunger hungry "
        "feast crop crops harvest kitchen spice spices tea coffee sugar salt milk diet"),
    "Care, learning": (
        "school student students teacher learn learning education study class doctor hospital medicine health "
        "sick disease nurse patient care"),
    "Arms": (
        "war wars battle battles army armies soldier soldiers weapon weapons sword fight fought attack defend "
        "defence invasion invade siege knight conquest military empire bomb tank"),
    "Tools": (
        "tool tools work worker workers farm farmer farming craft craftsman build building built repair dig "
        "plough labour"),
    "Music, play, sport": (
        "music song songs dance play played game games sport sports festival celebration fun toy toys"),
    "Law": (
        "law court courts judge justice crime police prison jail arrest right rights constitution parliament "
        "government vote election protest citizen citizens democracy"),
    "Getting about": (
        "travel travelled journey road roads car cars bus train railway ship ships boat boats plane flight "
        "transport trade route traffic move moved migration"),
    "Places": (
        "city cities town towns village villages temple church mosque palace castle fort building buildings "
        "capital monument school hospital bank market"),
    "Land and water": (
        "river rivers lake sea ocean coast coastal beach island mountain mountains hill hills valley desert "
        "forest jungle land landscape geography climate rain monsoon flood floods delta plain plains plateau "
        "north south east west region terrain water"),
    "Nature": (
        "nature tree trees forest plant plants flower flowers animal animals weather rain sun sunny cloud storm "
        "snow season seasons volcano earthquake"),
    "Environment, water, power": (
        "environment pollution waste recycle water drinking clean dirty electricity power energy climate plastic"),
    "India": (
        "india indian bharat village gandhi delhi mumbai bengal punjab raj mughal festival diwali holi chai"),
    "First farmers, first cities": (
        "ancient prehistoric prehistory stone hunter hunters gatherer gatherers farming farmers first settle "
        "settled settlement neolithic city cities mesopotamia sumer sumerian uruk ur babylon clay tablet writing "
        "cuneiform temple ziggurat bronze copper trade irrigation canal river harvest grain barley"),
}

# A few everyday things every shot is shown (a table, a book, a house, a tree...).
CORE = "table chair book scroll document letter coins moneybag crown house hut tree mountain river cloud sun flagpole road village sack basket".split()

# Other names things go by (what a model or a person may write): the drawn thing each is.
ALIASES = {"bag": "moneybag", "purse": "moneybag", "money": "moneybag", "gold": "coins", "treasure": "chest",
           "coinpile": "coins", "notes": "cash", "banknotes": "cash", "jewel": "gem", "diamond": "gem",
           "ruby": "gem", "tome": "book", "paper": "document", "contract": "document", "deed": "charter",
           "decree": "charter", "treaty": "charter", "envelope": "letter", "map": "oldmap", "featherpen": "quill",
           "throne_chair": "throne", "cupboard": "bookshelf", "shelf": "bookshelf", "grain": "sack", "matka": "pot",
           "amphora": "jar", "lamp": "diya", "fire": "campfire", "plow": "plough",
           "spinningwheel": "charkha", "balance": "scales", "timer": "hourglass", "chalice": "goblet", "idea": "lightbulb",
           "press": "printingpress", "sign": "signpost",
           "flag": "flagpole", "wagon": "cart", "bullockcart": "cart", "cottage": "hut", "home": "house",
           "moneybox": "piggybank", "creditcard": "card", "bill": "receipt", "vault": "safe", "marketstall": "stall",
           "pen": "pencil", "copy": "notebook", "file": "folder", "files": "folder", "mobile": "phone",
           "smartphone": "phone", "telephone": "oldphone", "television": "tv", "mic": "microphone",
           "loudspeaker": "megaphone", "ballot": "ballotbox", "watch": "clock", "magnifyingglass": "magnifier",
           "cup": "trophy", "award": "medal", "beaker": "flask", "chemistry": "flask", "cog": "gear",
           "spaceship": "rocket", "solar": "solarpanel", "mill": "factory", "oil": "oilwell", "loaf": "bread",
           "rice": "bowl", "food": "thali", "chai": "kulhad", "tea": "teacup", "milk": "milkcan",
           "medicine": "pills", "firstaid": "medkit", "injection": "syringe", "vaccine": "syringe", "cycle": "bicycle",
           "bike": "bicycle", "auto": "autorickshaw", "tuktuk": "autorickshaw", "locomotive": "train",
           "aeroplane": "plane", "airplane": "plane", "coach": "carriage", "fortress": "castle", "fort": "castle",
           "mahal": "palace", "mandir": "temple", "masjid": "mosque", "cathedral": "church", "college": "school",
           "store": "shop", "building": "skyscraper", "hill": "mountain", "peak": "mountain", "rose": "flower",
           "lock": "padlock", "present": "gift", "cricket": "cricketbat", "explosive": "bomb", "carpet": "rug",
           "flags": "bunting", "rifle": "musket", "tiranga": "flagindia", "indianflag": "flagindia", "cot": "charpai",
           "top": "lattu", "dabba": "tiffin",
           "trebuchet": "catapult", "armour": "armor", "suitofarmor": "armor", "standard": "banner", "trumpet": "horn",
           "bugle": "horn", "knife": "dagger", "cannonball": "cannonballs", "pyramid": "pyramids", "column": "pillar",
           "handloom": "loom", "shankh": "conch", "bansuri": "flute", "palki": "palanquin", "stove": "chulha",
           "pump": "handpump", "hay": "haystack", "masala": "spices", "globe": "deskglobe", "turbine": "windturbine",
           "powerline": "pylon", "lamppost": "streetlight", "signal": "trafficlight", "board": "whiteboard",
           "chalkboard": "blackboard", "petrolpump": "fuelpump", "gaspump": "fuelpump", "shippingcontainer": "container",
           "trolley": "shoppingcart", "price": "pricetag", "till": "cashregister", "luggage": "suitcase",
           "schoolbag": "backpack", "couch": "sofa", "desklamp": "tablelamp", "wok": "pan", "dish": "plate",
           "pitcher": "jug", "postbox": "mailbox", "refrigerator": "fridge", "boot": "shoe", "clothes": "shirt",
           "pine": "pinetree", "rain": "raincloud", "thunder": "lightning", "snow": "snowflake", "seedling": "sprout",
           "seed": "sprout", "honey": "beehive", "eggs": "nest", "firewood": "logs", "fever": "thermometer",
           "love": "heart", "graduation": "gradcap", "degree": "diploma", "certificate": "diploma",
           "spade": "shovel", "pick": "pickaxe", "hasiya": "sickle", "scythe": "sickle", "fork": "pitchfork",
           "barrow": "wheelbarrow", "tools": "toolbox", "brush": "paintbrush", "canvas": "easel", "painting": "easel",
           "birthday": "cake", "chilli": "chili", "mirchi": "chili", "pepper": "chili", "ladoo": "laddoo",
           "sweets": "laddoo", "mithai": "laddoo", "ganna": "sugarcane", "chapati": "roti", "cooker": "pressurecooker",
           "pestle": "mortar", "lpg": "gascylinder", "cylinder": "gascylinder", "keyboard": "piano",
           "tabletennis": "racket", "badminton": "racket", "tennis": "racket", "gym": "dumbbell", "hockey": "hockeystick",
           "chess": "chessboard", "cards": "playingcards", "joystick": "gamecontroller", "videogame": "gamecontroller",
           "wifi": "router", "internet": "router", "satdish": "satellitedish", "dth": "satellitedish", "surveillance": "cctv", "microchip": "chip",
           "semiconductor": "chip", "ipad": "tablet", "celltower": "mobiletower", "tower5g": "mobiletower",
           "socket": "plug", "electricity": "plug", "germ": "virus", "bacteria": "virus", "covid": "virus",
           "saturn": "planet", "world": "earth", "asteroid": "comet", "meteor": "comet", "burner": "bunsen",
           "doctor": "stethoscope", "plaster": "bandage", "motorbike": "motorcycle",
           "moped": "scooter", "chopper": "helicopter", "airballoon": "hotairballoon", "yacht": "sailboat",
           "kayak": "canoe", "firebrigade": "firetruck", "fireengine": "firetruck", "police": "policecar",
           "army": "jeep", "jcb": "bulldozer", "fighterjet": "jet", "airforce": "jet", "streetcar": "tram",
           "sansad": "parliament", "assembly": "parliament", "courthouse": "court", "judiciary": "court",
           "jail": "prison", "reservoir": "dam", "granary": "silo", "godown": "warehouse",
           "taj": "tajmahal", "eiffel": "eiffeltower", "rome": "colosseum", "chinawall": "greatwall",
           "nuclear": "powerplant", "coolingtower": "powerplant", "date": "calendar", "pass": "ticket",
           "visa": "passport", "aadhaar": "idcard", "identity": "idcard", "check": "cheque", "package": "parcel",
           "delivery": "parcel", "sceptre": "scepter", "glasses": "spectacles", "specs": "spectacles",
           "jewellery": "necklace", "jewelry": "necklace", "haar": "necklace", "votingmachine": "evm",
           "extinguisher": "fireextinguisher", "cyclone": "tornado",
           "storm": "tornado", "twister": "tornado", "flame": "torch", "mashaal": "torch", "judge": "gavel",
           "arrest": "handcuffs",
           "grainofwheat": "kernel", "wheatgrain": "kernel", "stoneaxe": "handaxe", "stonetool": "handaxe",
           "stonetools": "handaxe", "flint": "flintknife", "blade": "flintknife", "rockart": "cavepainting",
           "shelter": "leanto", "grindstone": "quern", "grindingstone": "quern",
           "pulses": "lentils", "dal2": "lentils", "peas": "peapod", "wool": "yarn", "thread": "yarn",
           "cloth": "clothbolt", "textile": "clothbolt", "fabric": "clothbolt", "granarypot": "storagejar",
           "copper": "copperore", "ore": "copperore", "tin": "ingot", "metal": "ingot", "bronze": "ingot",
           "shell": "seashell", "lapislazuli": "lapis", "tablet2": "claytablet", "cuneiform": "claytablet",
           "reed": "stylus", "clay": "claylump", "temple2": "ziggurat", "bricks": "mudbricks", "brick": "mudbricks",
           "wall": "citywall", "citywalls": "citywall", "inscription": "stele", "seal2": "cylinderseal",
           "conemosaic": "claycones", "wheel2": "potterswheel", "harp": "lyre", "datefruit": "dates",
           "riverboat": "barge", "irrigation": "shaduf", "channel": "canal", "leather": "hide",
           "lamp2": "oillamp", "package2": "sealing", "signalfire": "beacon", "library": "tabletshelf",
           "archive": "tabletshelf", "farmland": "field", "furrows": "field", "net": "fishingnet",
           "stream": "river", "brook": "river", "pond": "lake", "falls": "waterfall", "hillside": "hills",
           "mountains": "mountainrange", "range": "mountainrange", "himalaya": "mountainrange", "himalayas": "mountainrange",
           "alps": "mountainrange", "everest": "snowpeak", "summit": "snowpeak", "gorge": "canyon", "sand": "dune",
           "sahara": "desert", "thar": "desert", "woods": "forest", "woodland": "forest", "rainforest": "jungle",
           "marsh": "swamp", "wetland": "swamp", "ice": "glacier", "seashore": "beach", "shore": "beach", "sea": "ocean",
           "coastline": "coast", "grassland": "meadow", "savanna": "acacia", "savannah": "acacia", "steppe": "meadow",
           "paddy": "terraces", "ricefields": "terraces", "coral": "reef", "hotspring": "geyser", "highway": "road",
           "street": "road", "path": "trail", "footpath": "trail", "town": "village", "city": "skyline", "harbour": "port",
           "harbor": "port", "dock": "port", "mineshaft": "mine", "dusk": "sunset", "sunrise": "sunset", "night": "nightsky",
           "stars": "nightsky", "laundry": "clothesline", "baby": "cradle", "chatai": "mat", "bin": "dustbin",
           "trashcan": "dustbin", "recycling": "recycle", "faucet": "tap", "pipeline": "pipe", "upi": "qrcode",
           "payment": "qrcode", "assemblyline": "conveyor", "automation": "robotarm", "monitor": "ecg",
           "heartmonitor": "ecg", "patient": "hospitalbed", "scan": "xray", "waste": "garbage", "trash": "garbage",
           "pollution": "smog", "smoke": "smog", "evcharger": "chargingstation", "cone": "trafficcone", "rails": "railtrack",
           "railway": "railtrack", "railwaystation": "station", "platform": "station", "lectern2": "podium",
           "protest": "placard", "election": "inkedfinger", "vote2": "inkedfinger", "samvidhan": "constitution",
           "kathputli": "puppet", "marsrover": "rover", "iss": "spacestation", "milkyway": "galaxy",
           "electriccircuit": "circuit", "mug": "coffee", "maize": "corn", "atombomb": "mushroomcloud",
           "explosion": "mushroomcloud", "rig": "oilrig", "blastfurnace": "furnace", "steelmill": "furnace",
           "morse": "telegraph", "engine": "steamengine"}

NAMES = tuple(sorted({n for v in SECTIONS.values() for n in v.split()}))
# The land, drawn to stand behind people (a river, hills, a forest): never moved off what stands on it, always behind.
SCENERY = frozenset(SECTIONS["Land and water"].split()) | {"mountain", "volcano", "island", "field", "canal", "terraces"}
SECTION_OF = {n: k for k, v in SECTIONS.items() for n in v.split()}


def known(name: str) -> str | None:
    n = str(name or "").lower().replace("-", "").replace("_", "")
    n = ALIASES.get(n, n)
    return n if n in SECTION_OF else None


def stand_in(name: str, of: str | None = None) -> str:
    """The picture a thing not on the shelf is drawn from: its plain words."""
    words = re.sub(r"[_\-]+", " ", str(name or "thing")).strip()
    return f"a {words}" + (f" of {of}" if of else "")


def _words(text: str) -> set[str]:
    ws = set(re.findall(r"[a-z]+", str(text or "").lower()))
    return ws | {w[:-1] for w in ws if w.endswith("s") and len(w) > 3} | {w[:-2] for w in ws if w.endswith("es") and len(w) > 4}


def shelf_for(text: str, most: int = 90) -> str:
    """The things a shot is shown, by section: those its words name, the sections its words call up (the ones called
    most first), and the everyday few; at most about `most` names."""
    ws = _words(text)
    named = []
    for w in sorted(ws):
        k = known(w)
        if k and k not in named:
            named.append(k)
    hits = sorted(((len(ws & set(KEYWORDS[s].split())), s) for s in SECTIONS), reverse=True)
    picked = {n: SECTION_OF[n] for n in named + CORE}
    first = True
    for score, sec in hits:
        if score == 0:
            break
        items = SECTIONS[sec].split()
        if not first and len(set(picked) | set(items)) > most:      # (the section called most comes whole)
            continue
        picked.update({n: sec for n in items})
        first = False
    groups: dict[str, list[str]] = {}
    for n, sec in picked.items():
        groups.setdefault(sec, []).append(n)
    return " | ".join(f"{sec.lower()}: {' '.join(groups[sec])}" for sec in SECTIONS if sec in groups)


def headings() -> str:
    """The sections, each with a few of its things (the whole shelf, told briefly)."""
    return "; ".join(f"{sec.lower()} ({len(v.split())}: {', '.join(v.split()[:5])}...)" for sec, v in SECTIONS.items())
