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
    return {"title": title, "index": index, "imageinfo": [{
        "url": f"http://127.0.0.1:{PORT['value']}/img/{name}", "thumburl": f"http://127.0.0.1:{PORT['value']}/img/{name}",
        "width": 1600, "height": 1000, "mime": "image/jpeg",
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

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path.startswith("/wiki/"):
            self._wiki(url.path.split("/")[2], urllib.parse.parse_qs(url.query))
            return
        if url.path.startswith("/img/"):
            title = "File:" + urllib.parse.unquote(url.path[5:])
            _l, _a, colour, words = FILES[title]
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
            words = q.get("gsrsearch", [""])[0].replace("filetype:bitmap", "").lower().split()
            titles = [t for t, (_l, _a, _c, keys) in FILES.items() if any(w in keys for w in words)]
        pages = {str(i): _page(i, t) for i, t in enumerate(titles, 1)}
        data = json.dumps({"query": {"pages": pages}} if pages else {}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
