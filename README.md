# CottagePlayer

Self-hosted media upload and playback service built with FastAPI, Alpine.js, Tailwind CSS, and Google OAuth.

## Features

- Google OAuth login with database-backed access control and roles (viewer, uploader, admin).
- Admin UI to review users, toggle activity, and promote/demote roles.
- Upload and stream audio, video, image, and GIF files.
- Responsive Alpine.js/Tailwind front-end.

## Requirements

- Python 3.11+
- Google Cloud OAuth client credentials with authorized redirect URI set to your deployment URL `/auth/callback`
- SQLite (bundled) or compatible SQL database

## Setup

1. Clone the repository and create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Create a `.env` file with the following variables:
   ```env
   GOOGLE_CLIENT_ID=your-google-client-id
   GOOGLE_CLIENT_SECRET=your-google-client-secret
   OAUTH_REDIRECT_URL=https://your-domain.com/auth/callback
   SESSION_SECRET=your-random-secret
   MEDIA_ROOT=/absolute/path/to/media
   DATABASE_URL=sqlite:///absolute/path/to/cottageplayer.db  # optional; defaults to MEDIA_ROOT/cottageplayer.db
   INITIAL_ADMIN_EMAILS=admin@example.com,another_admin@example.com
   ALLOW_AUTO_SIGNUP=false
   ```

3. Run the application:
   ```bash
   uvicorn app.main:app --reload
   ```

4. Navigate to `http://localhost:8000`:
   - If you're not authenticated you'll be redirected to `/auth-required` with a Google sign-in button.
   - After authenticating with an admin account you can manage users at `/admin/users`.

## Environment Variables

- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: Credentials from Google Cloud Console.
- `OAUTH_REDIRECT_URL`: Must match the redirect configured in Google Cloud.
- `SESSION_SECRET`: Random string used for session signing.
- `MEDIA_ROOT`: Optional path to store uploaded media. Defaults to `app/storage/media`.
- `DATABASE_URL`: Optional SQLAlchemy database URL (SQLite by default).
- `INITIAL_ADMIN_EMAILS`: Comma-separated list of emails to seed as admins on startup.
- `ALLOW_AUTO_SIGNUP`: Defaults to `false`. Set to `true` to automatically provision accounts on first login.

## Roles

- `viewer`: Can log in and play media.
- `uploader`: Viewer privileges plus ability to upload new media.
- `admin`: Full access, including managing users and toggling activity.

## Notes

- Media files are stored on the filesystem; ensure the directory is writable.
- Sessions use signed cookies. For production deployment configure TLS and strong secrets.
- To reseed admins update `INITIAL_ADMIN_EMAILS` and restart the service.
- `/auth/status` reports the current session's authentication state for client-side checks.
