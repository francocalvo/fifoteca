import logging
from pathlib import Path

from sqlmodel import Session, create_engine, select

from app import crud
from app.core.config import settings
from app.models import User, UserCreate

logger = logging.getLogger(__name__)

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.models
    # SQLModel.metadata.create_all(engine)

    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = crud.create_user(session=session, user_create=user_in)

    # Seed default dev users (idempotent)
    dev_users = [
        {"full_name": "Franco", "email": "dev@francocalvo.ar", "password": "calvo123"},
        {"full_name": "Manuel", "email": "manuel@francocalvo.ar", "password": "calvo123"},
    ]
    for dev_user in dev_users:
        existing = session.exec(
            select(User).where(User.email == dev_user["email"])
        ).first()
        if not existing:
            crud.create_user(
                session=session,
                user_create=UserCreate(
                    email=dev_user["email"],
                    password=dev_user["password"],
                    full_name=dev_user["full_name"],
                ),
            )

    # Seed FIFA data from bundled CSV (idempotent — skips existing records)
    from app.scripts.seed_fifa_data import parse_csv, seed_fifa_data

    csv_path = Path(__file__).resolve().parent.parent.parent / "data" / "fifa_teams.csv"
    if csv_path.exists():
        rows = parse_csv(csv_path)
        stats = seed_fifa_data(session, rows)
        created = stats["leagues_created"] + stats["teams_created"]
        if created > 0:
            logger.info(
                "FIFA seed: %d leagues, %d teams created",
                stats["leagues_created"],
                stats["teams_created"],
            )
    else:
        logger.warning("FIFA CSV not found at %s — skipping seed", csv_path)
