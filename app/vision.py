"""Photo intake: read one grocery photo with a vision model. Backend chosen by env:
  OLLAMA_URL (default http://localhost:11434) + VISION_MODEL (default qwen2.5vl:7b)  -> free, local
  VISION_BACKEND=groq + GROQ_API_KEY + GROQ_MODEL                                     -> hosted fallback
Set VISION_BACKEND=off (the VPS default) to hide photo intake and keep only the manual form."""
import base64, io, json, os, re, requests
import pillow_heif
from PIL import Image, ImageOps

pillow_heif.register_heif_opener()
BACKEND = os.environ.get("VISION_BACKEND", "ollama")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("VISION_MODEL", "qwen2.5vl:7b")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
CATS = ("produce, dairy, refrigerated meal, frozen meal, frozen meat, frozen seafood, frozen dumplings, "
        "frozen bread, frozen vegetable, noodles, pasta, pasta sauce, sauce, seasoning, stock, dashi, dried goods, "
        "furikake, soup mix, sauce mix, roux, rice mix, baking, snack, dessert, other")
PROMPT = ("This is a photo of one packaged grocery item (labels may be Japanese). Reply with JSON only, keys: "
          f"name (product name in English, include brand), category (one of: {CATS}), "
          "best_by (printed best-by / 賞味期限 date as YYYY-MM-DD or YYYY-MM, or null if not visible), "
          "quantity (how many identical packages are visible, integer).")


def enabled():
    return BACKEND != "off"


def to_jpeg(raw: bytes, max_side=1600) -> bytes:
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def read(jpeg: bytes) -> dict:
    b64 = base64.b64encode(jpeg).decode()
    if BACKEND == "groq":
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": "Bearer " + os.environ["GROQ_API_KEY"]},
                          json={"model": GROQ_MODEL, "temperature": 0, "response_format": {"type": "json_object"},
                                "messages": [{"role": "user", "content": [
                                    {"type": "text", "text": PROMPT},
                                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]}]},
                          timeout=120)
        r.raise_for_status()
        txt = r.json()["choices"][0]["message"]["content"]
    else:
        r = requests.post(OLLAMA_URL + "/api/chat",
                          json={"model": MODEL, "stream": False, "format": "json", "options": {"temperature": 0},
                                "messages": [{"role": "user", "content": PROMPT, "images": [b64]}]}, timeout=300)
        r.raise_for_status()
        txt = r.json()["message"]["content"]
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else {}
