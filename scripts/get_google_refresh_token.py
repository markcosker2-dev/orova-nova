"""One-time helper: generate a GOOGLE_REFRESH_TOKEN for Drive backups.

Why this exists: vault_skill.py backs up Nova's SQLite to Google Drive so the
DB (leads + learning data) survives Render's ephemeral-disk redeploys. A
*service account* (GOOGLE_CREDENTIALS_JSON) can list/read Drive but CANNOT
upload files — Google grants service accounts no Drive storage quota, so an
upload returns 403 "storageQuotaExceeded". Uploading requires authenticating
as a real Google user via OAuth, which needs a refresh token. This runs the
one-time consent flow and prints it.

Usage (locally, on a machine with a browser):

    python scripts/get_google_refresh_token.py

It reads GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET from the environment or a local
.env, or prompts for them. Approve access in the browser window that opens,
then set all three values on Render (Environment tab):
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN.

The OAuth client (Google Cloud Console -> APIs & Services -> Credentials) must
be of type "Desktop app". If you created a "Web application" client, either
recreate it as a Desktop app or add http://localhost to its authorized
redirect URIs — otherwise Google returns redirect_uri_mismatch.
"""
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SCOPES = ["https://www.googleapis.com/auth/drive"]


def main() -> int:
    client_id = os.getenv("GOOGLE_CLIENT_ID") or input("Google OAuth Client ID: ").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET") or input("Google OAuth Client secret: ").strip()
    if not client_id or not client_secret:
        print("ERROR: both client id and secret are required.")
        return 1

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERROR: dependency missing — run `pip install google-auth-oauthlib`.")
        return 1

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    # access_type=offline + prompt=consent guarantees a refresh_token comes back
    # (Google omits it on repeat consents otherwise).
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        print("\nERROR: no refresh token returned. Revoke prior access at "
              "https://myaccount.google.com/permissions and re-run.")
        return 1

    print("\n" + "=" * 64)
    print("SUCCESS — set these THREE on Render (Environment tab), then Save:")
    print("=" * 64)
    print(f"GOOGLE_CLIENT_ID={client_id}")
    print(f"GOOGLE_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print("=" * 64)
    print("Backups will then upload to your Drive (folder: OROVA_BACKUPS).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
