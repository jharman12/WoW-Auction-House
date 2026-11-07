# WoW Auction House

A local-network auction house for a D&D campaign. This repository is at
Phase 0: the application foundation is in place; marketplace features are
not implemented yet.

## Requirements

- Python 3.12 or newer
- Windows or Linux

## Setup

From the repository root, create and activate a virtual environment.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Linux:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

```sh
python app.py
```

Open `http://localhost:8050` on the host computer. The server binds to
`0.0.0.0` by default so other devices on the same trusted local network can
connect using the host computer's LAN IP and port 8050. The host's firewall
may need to allow inbound connections on that port for private networks.
No firewall rules are changed automatically. This app has no authentication
and is intended only for a trusted LAN; do not expose it to the public
internet.

Configuration is read from environment variables prefixed with `AUCTION_`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AUCTION_HOST` | `0.0.0.0` | Bind address |
| `AUCTION_PORT` | `8050` | Web server port |
| `AUCTION_DATABASE_PATH` | `instance/auction_house.db` | SQLite database path |
| `AUCTION_LOG_LEVEL` | `INFO` | Log verbosity |
| `AUCTION_LOG_PATH` | `logs/auction_house.log` | Log file path |

Other simulation and economy defaults are centralized in `config.py` for
later phases. They do not activate background jobs in Phase 0.

## Database And Backups

The SQLite database is created under `instance/` on first startup and
upgraded with Alembic migrations. To back it up, stop the application and
copy `instance/auction_house.db` to a dated backup location. To restore,
stop the application and replace the database file with the backup. Keep
the backup outside the repository. The database and logs are ignored by
Git.

## Tests

```sh
python -m pytest
```

The tests cover configuration validation, database migration and
persistence, and the basic Dash response. LAN reachability from a second
device must be verified on the campaign network.