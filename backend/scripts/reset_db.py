"""Drop everything and rebuild the schema from the current models.

initialize_database only ever adds missing tables, so a new column on an existing model
never reaches a database that has already been created. While the data is disposable,
rebuilding is the quickest way to pick up a model change. This also clears uploaded
knowledge chunks, so those PDFs need re-uploading afterwards.

Run from the backend folder:
    python -m scripts.reset_db
    python -m scripts.reset_db --yes --admin-email you@example.com --admin-password "..." --demo
"""

import argparse
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db import Base, Role, SessionLocal, engine, initialize_database, is_sqlite
from scripts.seed import seed_demo, seed_public_demo, seed_rich_demo, upsert_user

MIN_PASSWORD_LENGTH = 8


def describe_target() -> str:
    return make_url(get_settings().database_url).render_as_string(hide_password=True)


def drop_everything() -> None:
    if is_sqlite:
        Base.metadata.drop_all(engine)
        return

    # Dropping the schema also clears tables left behind by renamed or deleted models,
    # which drop_all keeps because it only knows about tables the models still declare.
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild the Master GYM schema from scratch.")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    parser.add_argument("--admin-email", help="Recreate this admin once the schema is back.")
    parser.add_argument("--admin-password")
    parser.add_argument("--admin-name", default="Master GYM Admin")
    parser.add_argument("--demo", action="store_true", help="Also add the demo trainer and member.")
    parser.add_argument(
        "--public-demo",
        action="store_true",
        help="Also add the read-only logins advertised on the sign-in page.",
    )
    parser.add_argument(
        "--rich-demo",
        action="store_true",
        help="Also add the full test dataset (trainers, members, classes, bookings, programmes).",
    )
    args = parser.parse_args()

    if args.admin_password and len(args.admin_password) < MIN_PASSWORD_LENGTH:
        print("Admin password must be at least 8 characters.", file=sys.stderr)
        return 1

    print(f"This deletes every table and row in:\n  {describe_target()}")
    if not args.yes and input("Type 'reset' to continue: ").strip().lower() != "reset":
        print("Cancelled.")
        return 1

    drop_everything()
    print("Dropped the old schema.")
    initialize_database()
    print("Recreated the tables and the default packages.")

    if args.admin_email and args.admin_password:
        with SessionLocal() as db:
            upsert_user(db, args.admin_email, args.admin_name, args.admin_password, Role.ADMIN)
            if args.demo:
                seed_demo(db)
            if args.public_demo:
                seed_public_demo(db)
            if args.rich_demo:
                seed_rich_demo(db)
            db.commit()
    else:
        print("Next: python -m scripts.seed --admin-email ... --admin-password ...")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
