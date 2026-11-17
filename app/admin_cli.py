"""Manage admin accounts on the server (the first one cannot be created in the browser).

    python -m app.admin_cli create <username>     asks for the password
    python -m app.admin_cli password <username>   new password, ends that admin's sessions
    python -m app.admin_cli delete <username>
    python -m app.admin_cli list

In Docker: docker compose exec -u appuser wegweiser python -m app.admin_cli create <username>
"""

import getpass
import sys

from app import auth, db


def _ask_password() -> str:
    while True:
        password = getpass.getpass("Passwort: ")
        if len(password) < auth.MIN_PASSWORD_LENGTH:
            print(f"Mindestens {auth.MIN_PASSWORD_LENGTH} Zeichen.")
            continue
        if getpass.getpass("Passwort wiederholen: ") != password:
            print("Die Passwörter stimmen nicht überein.")
            continue
        return password


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("create", "password", "delete", "list") \
            or (argv[0] != "list" and len(argv) != 2):
        print(__doc__.strip())
        return 2
    command, name = argv[0], (argv[1].strip() if len(argv) > 1 else "")
    with db.get_conn() as conn:
        db.migrate(conn)
        found = db.get_admin_credentials(conn, name) if name else None
        if command == "list":
            for admin in db.list_admins(conn):
                print(admin.username)
            return 0
        if command == "create":
            if found:
                print(f"Admin „{name}“ gibt es schon.")
                return 1
            db.create_admin(conn, name, auth.hash_password(_ask_password()))
            print(f"Admin „{name}“ angelegt.")
            return 0
        if not found:
            print(f"Admin „{name}“ nicht gefunden.")
            return 1
        if command == "password":
            db.set_admin_password(conn, found[0].id, auth.hash_password(_ask_password()))
            print("Passwort geändert, bestehende Anmeldungen beendet.")
        else:
            db.delete_admin(conn, found[0].id)
            print(f"Admin „{name}“ gelöscht.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
