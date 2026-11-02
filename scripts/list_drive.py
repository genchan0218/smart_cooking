import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
key, folder = sys.argv[1], sys.argv[2]
creds = service_account.Credentials.from_service_account_file(key, scopes=["https://www.googleapis.com/auth/drive.readonly"])
svc = build("drive", "v3", credentials=creds)
try:
    meta = svc.files().get(fileId=folder, fields="id,name", supportsAllDrives=True).execute()
    print("Folder:", meta["name"])
except Exception as e:
    print("ERROR accessing folder:", str(e)[:300]); sys.exit(1)
page = None; n = 0
while True:
    r = svc.files().list(q=f"'{folder}' in parents and trashed=false", fields="nextPageToken, files(id,name,mimeType,size)", pageSize=200, pageToken=page, supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    for f in r["files"]:
        n += 1; print(f["mimeType"], "|", f["name"], "|", f.get("size"), "|", f["id"])
    page = r.get("nextPageToken")
    if not page: break
print("Total:", n)
