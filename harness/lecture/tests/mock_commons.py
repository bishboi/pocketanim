"""A stand-in for the Wikimedia Commons API (query + imageinfo + extmetadata), its image server, and
Wikipedia's API (pageimages, langlinks, search) under /wiki/<lang>/.

Search results include one file under a licence a video may not reuse, which
the client must skip; one Wikipedia article leads with a non-free local image
that Commons does not have, which the client must not use.
"""
import io
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler

FILES = {
    "File:Sugarcane field in Uttar Pradesh.jpg": ("CC BY-SA 4.0", "A. Farmer", "#5E8C31", "sugarcane"),
    "File:Sugarcane harvest (restricted).jpg": ("All rights reserved", "Someone", "#999999", "sugarcane"),
    "File:Wheat harvest India.jpg": ("CC0", "B. Grower", "#D9A441", "wheat"),
    "File:Ganges at Varanasi.jpg": ("Public domain", "C. Boatman", "#3E7CB1", "ganges varanasi river"),
    "File:Thar desert dunes Rajasthan.jpg": ("CC BY 2.0", "D. Traveller", "#D8A25E", "rajasthan thar desert climate"),
    "File:Chipko movement women hugging trees.jpg": ("CC BY-SA 4.0", "E. Walker", "#3C7A3E", "zz-no-search"),
    "File:Sunderlal Bahuguna portrait.jpg": ("CC BY 2.0", "F. Lens", "#8A6A4A", "zz-no-search"),
    # Diagrams: SVG drawings, served as Commons' PNG rendering.
    "File:Wheat plant labelled diagram.svg": ("CC BY-SA 3.0", "G. Botanist", "#E8D9A8", "wheat plant diagram crop"),
    "File:Tractor farming illustration.svg": ("CC0", "H. Drafter", "#D6E4C8", "tractor tractors farming illustration"),
    "File:Water cycle diagram.svg": ("CC BY 4.0", "I. Teacher", "#CFE3F2", "water cycle diagram rain"),
    "File:Company logo.svg": ("CC0", "J. Brand", "#FFFFFF", "wheat tractor water logo"),     # not educational
}
# Wikipedia articles: title -> (lead image file name, English title for a Hindi article).
WIKI = {
    "en": {"Chipko movement": ("Chipko movement women hugging trees.jpg", None),
           "Sunderlal Bahuguna": ("Sunderlal Bahuguna portrait.jpg", None),
           "Some Film": ("Some Film poster.jpg", None)},          # non-free, local to Wikipedia: not on Commons
    "hi": {"चिपको आन्दोलन": (None, "Chipko movement")},             # the Hindi article has no picture
}
PORT = {"value": 0}


def _jpeg(colour: str, label: str) -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1600, 1000), colour)
    draw = ImageDraw.Draw(image)
    for i in range(0, 1600, 80):
        draw.line([(i, 1000), (i + 300, 0)], fill="#FFFFFF", width=6)
    draw.rectangle((500, 420, 1100, 580), fill="#000000")
    draw.text((540, 480), label, fill="#FFFFFF")
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


def _page(index: int, title: str) -> dict:
    licence, artist, _colour, _words = FILES[title]
    name = urllib.parse.quote(title.removeprefix("File:"))
    svg = title.endswith(".svg")
    thumb = f"http://127.0.0.1:{PORT['value']}/img/{name}" + (".png" if svg else "")
    return {"title": title, "index": index, "imageinfo": [{
        "url": f"http://127.0.0.1:{PORT['value']}/img/{name}", "thumburl": thumb,
        "width": 512 if svg else 1600, "height": 320 if svg else 1000, "mime": "image/svg+xml" if svg else "image/jpeg",
        "extmetadata": {"LicenseShortName": {"value": licence}, "Artist": {"value": f'<a href="#">{artist}</a>'},
                        "ImageDescription": {"value": f"<p>{title[5:-4]}</p>"}}}]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _wiki(self, lang: str, q: dict) -> None:
        articles = WIKI.get(lang, {})
        if q.get("list") == ["search"]:
            words = q["srsearch"][0].lower().split()
            self._json({"query": {"search": [{"title": t} for t in articles if any(w in t.lower() for w in words)]}})
            return
        pages = []
        for title in q["titles"][0].split("|"):
            match = next((t for t in articles if t.lower() == title.lower()), None)     # redirects: case and aliases
            if match is None:
                pages.append({"title": title, "missing": True})
                continue
            image, english = articles[match]
            page = {"title": match}
            if image:
                page["pageimage"] = image.replace(" ", "_")
            if english:
                page["langlinks"] = [{"lang": "en", "title": english}]
            pages.append(page)
        self._json({"query": {"pages": pages}})

    def _sources(self, url) -> bool:
        """NASA, The Met and the Smithsonian, as their APIs answer."""
        q = urllib.parse.parse_qs(url.query)
        port = PORT["value"]
        img = lambda name: f"http://127.0.0.1:{port}/img/{urllib.parse.quote(name)}"  # noqa: E731
        if url.path == "/nasa/search":
            items = []
            if "earth" in q.get("q", [""])[0].lower() or "cloud" in q.get("q", [""])[0].lower():
                items = [{"data": [{"nasa_id": "earth01", "title": "Earth clouds from orbit",
                                    "description": "Clouds over the Earth seen from the ISS", "center": "JSC"}],
                          "links": [{"href": img("Earth clouds~large.jpg"), "rel": "preview"}]},
                         {"data": [{"nasa_id": "earth02", "title": "Earth cloud art",
                                    "description": "Copyright someone else"}],
                          "links": [{"href": img("Earth clouds~large.jpg")}]}]
            self._json({"collection": {"items": items}})
            return True
        if url.path == "/met/search":
            self._json({"total": 2, "objectIDs": [11, 12]} if "akbar" in q.get("q", [""])[0].lower() else {"total": 0})
            return True
        if url.path.startswith("/met/objects/"):
            object_id = int(url.path.rsplit("/", 1)[1])
            self._json({"objectID": object_id, "isPublicDomain": object_id == 11, "title": "Akbar hunting",
                        "objectDate": "ca. 1600", "artistDisplayName": "Basawan", "objectName": "Folio",
                        "primaryImage": img("Akbar folio.jpg")})
            return True
        if url.path == "/si/search":
            rows = []
            if "sword" in q.get("q", [""])[0].lower():
                rows = [{"id": "si1", "title": "Mughal sword", "content": {"descriptiveNonRepeating": {
                    "data_source": "Freer Gallery of Art", "online_media": {"media": [
                        {"type": "Images", "content": img("Mughal sword.jpg"), "usage": {"access": "CC0"}}]}}}},
                        {"id": "si2", "title": "Mughal sword replica", "content": {"descriptiveNonRepeating": {
                            "online_media": {"media": [{"type": "Images", "content": img("x.jpg"),
                                                        "usage": {"access": "Usage conditions apply"}}]}}}}]
            self._json({"response": {"rows": rows}})
            return True
        return False

    def do_POST(self):
        """OpenRouter's chat completions with image output: one PNG, as a data URL."""
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        from PIL import Image

        out = io.BytesIO()
        Image.new("RGB", (1024, 640), "#88AACC").save(out, format="PNG")
        data = "data:image/png;base64," + __import__("base64").b64encode(out.getvalue()).decode()
        PORT.setdefault("prompts", []).append(body)
        self._json({"choices": [{"message": {"role": "assistant", "content": "",
                                             "images": [{"type": "image_url", "image_url": {"url": data}}]}}]})

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if self._sources(url):
            return
        if url.path.startswith("/wiki/"):
            self._wiki(url.path.split("/")[2], urllib.parse.parse_qs(url.query))
            return
        if url.path.startswith("/openverse/"):
            self._json({"results": []})
            return
        if url.path.startswith("/img/"):
            title = "File:" + urllib.parse.unquote(url.path[5:]).removesuffix(".svg.png").removesuffix(".png")
            if title + ".svg" in FILES:
                title += ".svg"
            elif not title.endswith((".jpg", ".svg")) and title + ".svg" in FILES:
                title += ".svg"
            _l, _a, colour, words = FILES.get(title, ("", "", "#777777", title[5:20]))
            data = _jpeg(colour, words)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        q = urllib.parse.parse_qs(url.query)
        if "titles" in q:
            titles = [t for t in (x.replace("_", " ") for x in q["titles"][0].split("|")) if t in FILES]
        else:
            search = q.get("gsrsearch", [""])[0]
            drawings = "filetype:drawing" in search
            words = search.replace("filetype:bitmap", "").replace("filetype:drawing", "").lower().split()
            words = [w for w in words if w != "diagram" or drawings]       # "... diagram filetype:bitmap": the topic
            titles = [t for t, (_l, _a, _c, keys) in FILES.items()
                      if any(w in keys.split() for w in words) and t.endswith(".svg") == drawings]
        pages = {str(i): _page(i, t) for i, t in enumerate(titles, 1)}
        data = json.dumps({"query": {"pages": pages}} if pages else {}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
