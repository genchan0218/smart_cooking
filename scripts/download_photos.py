import sys, io, os, json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pillow_heif
from PIL import Image, ImageOps
pillow_heif.register_heif_opener()
key, folder, out = sys.argv[1], sys.argv[2], sys.argv[3]
orig, jpg = os.path.join(out, "original"), os.path.join(out, "jpg")
os.makedirs(orig, exist_ok=True); os.makedirs(jpg, exist_ok=True)
svc = build("drive", "v3", credentials=service_account.Credentials.from_service_account_file(key, scopes=["https://www.googleapis.com/auth/drive.readonly"]))
files, page = [], None
while True:
    r = svc.files().list(q=f"'{folder}' in parents and trashed=false", fields="nextPageToken, files(id,name,mimeType,size,createdTime,modifiedTime,imageMediaMetadata(time))", pageSize=200, pageToken=page).execute()
    files += r["files"]; page = r.get("nextPageToken")
    if not page: break
seen, manifest = set(), []
for f in sorted(files, key=lambda x: x["name"]):
    key_ = (f["name"], f.get("size"))
    if key_ in seen: continue
    seen.add(key_)
    path = os.path.join(orig, f["name"])
    if not os.path.exists(path):
        with open(path, "wb") as fh:
            d = MediaIoBaseDownload(fh, svc.files().get_media(fileId=f["id"]))
            done = False
            while not done: _, done = d.next_chunk()
    taken = None
    if f["name"].lower().endswith(".heic"):
        im = Image.open(path)
        try: taken = im.getexif().get_ifd(0x8769).get(0x9003) or im.getexif().get(306)
        except Exception: pass
        im = ImageOps.exif_transpose(im).convert("RGB"); im.thumbnail((1600, 1600))
        im.save(os.path.join(jpg, os.path.splitext(f["name"])[0] + ".jpg"), quality=85)
    manifest.append({"name": f["name"], "taken": taken, "drive_created": f["createdTime"], "mime": f["mimeType"]})
json.dump(manifest, open(os.path.join(out, "manifest.json"), "w"), indent=1)
print("unique files:", len(manifest), "| with EXIF date:", sum(1 for m in manifest if m["taken"]))
print("first/last taken:", min((m["taken"] for m in manifest if m["taken"]), default=None), max((m["taken"] for m in manifest if m["taken"]), default=None))
