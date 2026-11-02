"""Read grocery photos with a local Ollama vision model and print/save what it sees.

usage: python vision_intake.py <out.json> <photo.jpg> [<photo.jpg> ...]
Runs against http://localhost:11434 (Ollama). No API key, no per-photo cost.
"""
import os, sys, json, base64, time, re, requests

MODEL = "qwen2.5vl:7b"
PROMPT = (
    "This is a photo of one packaged grocery item (labels may be Japanese). "
    "Reply with JSON only, keys: name (product name in English, include brand), "
    "category (one of: sauce, noodles, frozen meal, frozen meat, frozen seafood, dairy, produce, "
    "dried goods, furikake, soup mix, roux, pasta, pasta sauce, seasoning, snack, other), "
    "best_by (printed best-by / 賞味期限 date as YYYY-MM-DD or YYYY-MM, or null if not visible), "
    "confidence (0-1)."
)


BACKEND = os.environ.get("VISION_BACKEND", "ollama")  # "ollama" (local, free) or "groq" (hosted)
# model ids change often: check console.groq.com/docs/vision for the current vision model
GROQ_MODEL = os.environ.get("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")


def read_photo(path):
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    t = time.time()
    if BACKEND == "groq":
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + os.environ["GROQ_API_KEY"]},
            json={"model": GROQ_MODEL, "temperature": 0, "response_format": {"type": "json_object"},
                  "messages": [{"role": "user", "content": [
                      {"type": "text", "text": PROMPT},
                      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]}]},
            timeout=120,
        )
        r.raise_for_status()
        txt = r.json()["choices"][0]["message"]["content"]
    else:
        r = requests.post(
            "http://localhost:11434/api/chat",
            json={"model": MODEL, "stream": False, "format": "json",
                  "messages": [{"role": "user", "content": PROMPT, "images": [b64]}],
                  "options": {"temperature": 0}},
            timeout=300,
        )
        r.raise_for_status()
        txt = r.json()["message"]["content"]
    try:
        data = json.loads(txt)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", txt, re.S)
        data = json.loads(m.group(0)) if m else {"raw": txt}
    data["seconds"] = round(time.time() - t, 1)
    return data


if __name__ == "__main__":
    out, photos = sys.argv[1], sys.argv[2:]
    res = {}
    for p in photos:
        name = p.replace("\\", "/").split("/")[-1]
        res[name] = read_photo(p)
        print(name, "->", res[name].get("name"), "|", res[name].get("category"),
              "|", res[name].get("best_by"), "|", res[name]["seconds"], "s", flush=True)
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
