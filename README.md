# CottagePlayer

Self-hosted media upload and playback service built with FastAPI, Alpine.js, Tailwind CSS, and Google OAuth.

## Features

- Google OAuth login with database-backed access control and roles (viewer, uploader, admin).
- Admin UI to review users, toggle activity, and promote/demote roles.
- Upload and stream audio, video, image, and GIF files.
- Responsive Alpine.js/Tailwind front-end.
- Curated library views for music, movies, TV, and photos with tag/playlist filtering.
- Inline pill selectors for tags and playlists to keep organisation consistent with the sidebar navigation.
- User-managed playlists (create, rename, describe, add/remove media) for music and other audio collections.

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
   TAG_OPTIONS=Music,Movie,TV,Photo,Podcast  # optional; comma-separated list for tag pills
   PLAYLIST_OPTIONS=Favorites,Music,Movies,TV Shows,Photos  # optional; comma-separated playlist names
   ```

3. Run the application:
   ```bash
   uvicorn app.main:app --reload
   ```

4. Navigate to `http://localhost:8000`:
   - If you're not authenticated you'll be redirected to `/auth-required` with a Google sign-in button.
   - After authenticating with an admin account you can manage users at `/admin/users`.
   - Use the sidebar to jump to dedicated library views (Music & Playlists, Movies, TV Shows, Photos & GIFs).
   - Manage playlists via the Music view: create, rename, add/remove items, and delete playlists directly from the UI.

## Environment Variables

- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: Credentials from Google Cloud Console.
- `OAUTH_REDIRECT_URL`: Must match the redirect configured in Google Cloud.
- `SESSION_SECRET`: Random string used for session signing.
- `MEDIA_ROOT`: Optional path to store uploaded media. Defaults to `app/storage/media`.
- `DATABASE_URL`: Optional SQLAlchemy database URL (SQLite by default).
- `INITIAL_ADMIN_EMAILS`: Comma-separated list of emails to seed as admins on startup.
- `ALLOW_AUTO_SIGNUP`: Defaults to `false`. Set to `true` to automatically provision accounts on first login.
- `TAG_OPTIONS`: Comma-separated tag catalogue exposed as pill selectors for uploads/filters.
- `PLAYLIST_OPTIONS`: Comma-separated playlist catalogue exposed as pill selectors for uploads/filters.

## Library organisation

The sidebar links correspond to filtered views on `/library/*`. Filters are pre-populated using the tag and playlist options defined in environment variables. Users with upload privileges can assign tags/playlists using pill selectors on upload or edit; viewers see badge chips on media cards and can browse via the curated sections. Playlists appear alongside filtered media so users can open or edit them quickly.

## Roles

- `viewer`: Can log in and play media.
- `uploader`: Viewer privileges plus ability to upload new media, assign tags/playlists, and manage personal playlists.
- `admin`: Full access, including managing users and toggling activity.

## Notes

- Media files are stored on the filesystem; ensure the directory is writable.
- Sessions use signed cookies. For production deployment configure TLS and strong secrets.
- To reseed admins update `INITIAL_ADMIN_EMAILS` and restart the service.
- `/auth/status` reports the current session's authentication state for client-side checks.
