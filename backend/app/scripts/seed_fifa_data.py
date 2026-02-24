import csv
import logging
import sys
import uuid
from pathlib import Path

from sqlmodel import Session, select

from app.core.db import engine
from app.models import FifaLeague, FifaTeam

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


HEADER_ALIASES: dict[str, str] = {
    # Lowercase short form (task spec format: team,league,att,mid,def)
    "team": "team",
    "league": "league",
    "att": "attack",
    "mid": "midfield",
    "def": "defense",
    # Title-case long form (bundled CSV format: Team,League,Attack,Midfield,Defence)
    "Team": "team",
    "League": "league",
    "Attack": "attack",
    "Midfield": "midfield",
    "Defence": "defense",
    # Optional columns
    "country": "country",
    "Country": "country",
}

REQUIRED_CANONICAL = {"team", "league", "attack", "midfield", "defense"}


def _normalize_headers(fieldnames: list[str]) -> dict[str, str]:
    """Map raw CSV column names to canonical internal names.

    Returns a dict mapping raw column name -> canonical name for all
    recognized columns.

    Raises ValueError if required canonical columns are missing.
    """
    mapping: dict[str, str] = {}
    for raw in fieldnames:
        canonical = HEADER_ALIASES.get(raw)
        if canonical is not None:
            mapping[raw] = canonical

    found_canonical = set(mapping.values())
    missing = REQUIRED_CANONICAL - found_canonical
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")

    return mapping


def parse_csv(csv_path: Path) -> list[dict]:
    """
    Parse CSV file and validate structure.

    Accepts two header formats:
    - Short lowercase: team,league,att,mid,def
    - Title-case long: Team,League,Attack,Midfield,Defence

    An optional 'Country' or 'country' column is used when present;
    otherwise the league name is used as the country fallback.

    Args:
        csv_path: Path to CSV file

    Returns:
        List of row dictionaries

    Raises:
        ValueError: If CSV structure is invalid
        FileNotFoundError: If CSV file doesn't exist
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError("CSV file is empty")

        header_map = _normalize_headers(list(reader.fieldnames))

        # Build reverse lookup: canonical -> raw column name
        canonical_to_raw: dict[str, str] = {}
        for raw, canonical in header_map.items():
            canonical_to_raw.setdefault(canonical, raw)

        team_col = canonical_to_raw["team"]
        league_col = canonical_to_raw["league"]
        attack_col = canonical_to_raw["attack"]
        midfield_col = canonical_to_raw["midfield"]
        defense_col = canonical_to_raw["defense"]
        country_col = canonical_to_raw.get("country")

        rows = []
        for row_num, row in enumerate(reader, start=2):
            try:
                att = int(row[attack_col])
                mid = int(row[midfield_col])
                defense = int(row[defense_col])

                if att < 0 or mid < 0 or defense < 0:
                    raise ValueError("Ratings must be non-negative")

                if att > 100 or mid > 100 or defense > 100:
                    raise ValueError("Ratings must be <= 100")

                league_name = row[league_col].strip()
                country = (
                    row[country_col].strip()
                    if country_col and row.get(country_col)
                    else league_name
                )

                rows.append(
                    {
                        "team_name": row[team_col].strip(),
                        "league_name": league_name,
                        "country": country,
                        "attack_rating": att,
                        "midfield_rating": mid,
                        "defense_rating": defense,
                    }
                )
            except ValueError as e:
                raise ValueError(f"Row {row_num}: {e}")

    return rows


def seed_fifa_data(session: Session, rows: list[dict]) -> dict[str, int]:
    """
    Seed FifaLeague and FifaTeam data from parsed CSV rows.

    Args:
        session: SQLAlchemy session
        rows: List of parsed row dictionaries

    Returns:
        Dictionary with counters:
            leagues_created, leagues_skipped, teams_created, teams_skipped
    """
    # Preload existing leagues
    existing_leagues = session.exec(select(FifaLeague)).all()
    league_map: dict[str, FifaLeague] = {
        league.name: league for league in existing_leagues
    }

    leagues_created = 0
    leagues_skipped = 0

    # Create missing leagues (collect country from first row per league)
    league_country: dict[str, str] = {}
    for row in rows:
        if row["league_name"] not in league_country:
            league_country[row["league_name"]] = row["country"]

    for league_name, country in league_country.items():
        if league_name in league_map:
            leagues_skipped += 1
            continue

        league = FifaLeague(name=league_name, country=country)
        session.add(league)
        leagues_created += 1

    # Flush to get IDs for newly created leagues
    session.flush()

    # Reload league map with new leagues
    existing_leagues = session.exec(select(FifaLeague)).all()
    league_map = {league.name: league for league in existing_leagues}

    # Preload existing teams
    existing_teams = session.exec(select(FifaTeam)).all()
    # Use (team_name, league_id) as deduplication key
    team_map: dict[tuple[str, uuid.UUID], FifaTeam] = {
        (t.name, t.league_id): t for t in existing_teams
    }

    teams_created = 0
    teams_skipped = 0

    # Create missing teams
    for row in rows:
        team_name = row["team_name"]
        league_name = row["league_name"]

        league = league_map.get(league_name)
        if not league:
            raise ValueError(f"League not found: {league_name}")

        # Check if team already exists in this league
        team_key = (team_name, league.id)
        if team_key in team_map:
            teams_skipped += 1
            continue

        # Compute overall rating
        overall_rating = (
            row["attack_rating"] + row["midfield_rating"] + row["defense_rating"]
        )

        team = FifaTeam(
            name=team_name,
            league_id=league.id,
            attack_rating=row["attack_rating"],
            midfield_rating=row["midfield_rating"],
            defense_rating=row["defense_rating"],
            overall_rating=overall_rating,
        )
        session.add(team)
        teams_created += 1

    session.commit()

    return {
        "leagues_created": leagues_created,
        "leagues_skipped": leagues_skipped,
        "teams_created": teams_created,
        "teams_skipped": teams_skipped,
    }


def main() -> None:
    """CLI entry point for seeding FIFA data from CSV."""
    if len(sys.argv) != 2:
        logger.error("Usage: python -m app.scripts.seed_fifa_data <path/to/csv>")
        sys.exit(1)

    csv_path = Path(sys.argv[1])

    logger.info(f"Parsing CSV file: {csv_path}")
    rows = parse_csv(csv_path)
    logger.info(f"Parsed {len(rows)} rows")

    logger.info("Seeding database...")
    with Session(engine) as session:
        stats = seed_fifa_data(session, rows)

    logger.info("Seeding complete!")
    logger.info(
        f"Leagues: {stats['leagues_created']} created, {stats['leagues_skipped']} skipped"
    )
    logger.info(
        f"Teams: {stats['teams_created']} created, {stats['teams_skipped']} skipped"
    )


if __name__ == "__main__":
    main()
