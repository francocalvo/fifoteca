from collections.abc import Generator
from pathlib import Path

import pytest
from sqlmodel import Session, delete, select

from app.models import FifaLeague, FifaTeam
from app.scripts import seed_fifa_data


@pytest.fixture
def clean_fifa_db(db: Session) -> Generator[Session, None, None]:
    """Clean up Fifoteca data before and after each test."""
    # Clean up before test
    db.exec(delete(FifaTeam))
    db.exec(delete(FifaLeague))
    db.commit()

    yield db

    # Clean up after test
    db.exec(delete(FifaTeam))
    db.exec(delete(FifaLeague))
    db.commit()


@pytest.fixture
def sample_csv_content() -> str:
    """Sample CSV content with multiple leagues and teams."""
    return """Country,Team,League,Attack,Midfield,Defence
Spain,Real Madrid,La Liga,90,88,85
Spain,Barcelona,La Liga,89,87,84
England,Manchester City,Premier League,91,89,86
England,Liverpool,Premier League,88,86,83
Germany,Bayern Munich,Bundesliga,87,85,82
Germany,Borussia Dortmund,Bundesliga,86,84,81
"""


@pytest.fixture
def sample_csv_file(tmp_path: Path, sample_csv_content: str) -> Path:
    """Create a temporary CSV file with sample data."""
    csv_file = tmp_path / "sample_teams.csv"
    csv_file.write_text(sample_csv_content)
    return csv_file


@pytest.fixture
def duplicate_league_csv() -> str:
    """CSV with repeated league names to test deduplication."""
    return """Country,Team,League,Attack,Midfield,Defence
CountryX,Team A,League X,80,80,80
CountryX,Team B,League X,75,75,75
CountryX,Team C,League X,70,70,70
CountryY,Team D,League Y,85,85,85
CountryY,Team E,League Y,82,82,82
"""


def test_parse_csv_valid_structure(sample_csv_file: Path) -> None:
    """Test that CSV parsing works with valid structure."""
    rows = seed_fifa_data.parse_csv(sample_csv_file)

    assert len(rows) == 6
    assert rows[0]["team_name"] == "Real Madrid"
    assert rows[0]["league_name"] == "La Liga"
    assert rows[0]["attack_rating"] == 90
    assert rows[0]["midfield_rating"] == 88
    assert rows[0]["defense_rating"] == 85


def test_parse_csv_missing_file(tmp_path: Path) -> None:
    """Test that FileNotFoundError is raised for missing file."""
    non_existent = tmp_path / "non_existent.csv"

    with pytest.raises(FileNotFoundError):
        seed_fifa_data.parse_csv(non_existent)


def test_parse_csv_missing_columns(tmp_path: Path) -> None:
    """Test that ValueError is raised for missing required columns."""
    csv_file = tmp_path / "bad_columns.csv"
    csv_file.write_text("Team,League,Attack,Midfield\nTeam A,League X,80,80")

    with pytest.raises(ValueError, match="CSV missing required columns"):
        seed_fifa_data.parse_csv(csv_file)


def test_parse_csv_invalid_ratings(tmp_path: Path) -> None:
    """Test that ValueError is raised for invalid rating values."""
    csv_file = tmp_path / "bad_ratings.csv"
    csv_file.write_text("Country,Team,League,Attack,Midfield,Defence\nX,Team A,League X,invalid,80,80")

    with pytest.raises(ValueError, match="Row 2"):
        seed_fifa_data.parse_csv(csv_file)


def test_parse_csv_negative_ratings(tmp_path: Path) -> None:
    """Test that ValueError is raised for negative ratings."""
    csv_file = tmp_path / "negative_ratings.csv"
    csv_file.write_text("Country,Team,League,Attack,Midfield,Defence\nX,Team A,League X,-10,80,80")

    with pytest.raises(ValueError, match="Row 2"):
        seed_fifa_data.parse_csv(csv_file)


def test_parse_csv_ratings_over_100(tmp_path: Path) -> None:
    """Test that ValueError is raised for ratings over 100."""
    csv_file = tmp_path / "high_ratings.csv"
    csv_file.write_text("Country,Team,League,Attack,Midfield,Defence\nX,Team A,League X,101,80,80")

    with pytest.raises(ValueError, match="Row 2"):
        seed_fifa_data.parse_csv(csv_file)


def test_seed_fifa_data_creates_leagues(
    clean_fifa_db: Session, sample_csv_file: Path
) -> None:
    """Test that leagues are created correctly from CSV."""
    rows = seed_fifa_data.parse_csv(sample_csv_file)
    stats = seed_fifa_data.seed_fifa_data(clean_fifa_db, rows)

    assert stats["leagues_created"] == 3
    assert stats["leagues_skipped"] == 0

    # Verify leagues in database
    leagues = clean_fifa_db.exec(select(FifaLeague)).all()
    assert len(leagues) == 3

    league_names = {league.name for league in leagues}
    assert league_names == {"La Liga", "Premier League", "Bundesliga"}

    # Verify country is set from CSV Country column
    league_countries = {league.name: league.country for league in leagues}
    assert league_countries["La Liga"] == "Spain"
    assert league_countries["Premier League"] == "England"
    assert league_countries["Bundesliga"] == "Germany"


def test_seed_fifa_data_league_deduplication(
    clean_fifa_db: Session, tmp_path: Path, duplicate_league_csv: str
) -> None:
    """Test that duplicate league names are handled correctly."""
    csv_file = tmp_path / "duplicate_leagues.csv"
    csv_file.write_text(duplicate_league_csv)

    rows = seed_fifa_data.parse_csv(csv_file)
    stats = seed_fifa_data.seed_fifa_data(clean_fifa_db, rows)

    # Should only create 2 unique leagues
    assert stats["leagues_created"] == 2
    assert stats["leagues_skipped"] == 0

    leagues = clean_fifa_db.exec(select(FifaLeague)).all()
    assert len(leagues) == 2


def test_seed_fifa_data_creates_teams(
    clean_fifa_db: Session, sample_csv_file: Path
) -> None:
    """Test that teams are created correctly from CSV."""
    rows = seed_fifa_data.parse_csv(sample_csv_file)
    stats = seed_fifa_data.seed_fifa_data(clean_fifa_db, rows)

    assert stats["teams_created"] == 6
    assert stats["teams_skipped"] == 0

    # Verify teams in database
    teams = clean_fifa_db.exec(select(FifaTeam)).all()
    assert len(teams) == 6

    # Check specific team
    real_madrid = clean_fifa_db.exec(
        select(FifaTeam).where(FifaTeam.name == "Real Madrid")
    ).first()
    assert real_madrid is not None
    assert real_madrid.attack_rating == 90
    assert real_madrid.midfield_rating == 88
    assert real_madrid.defense_rating == 85


def test_seed_fifa_data_team_league_linkage(
    clean_fifa_db: Session, sample_csv_file: Path
) -> None:
    """Test that teams are linked to correct leagues."""
    rows = seed_fifa_data.parse_csv(sample_csv_file)
    seed_fifa_data.seed_fifa_data(clean_fifa_db, rows)

    # Get La Liga
    la_liga = clean_fifa_db.exec(
        select(FifaLeague).where(FifaLeague.name == "La Liga")
    ).first()
    assert la_liga is not None

    # Get teams in La Liga
    la_liga_teams = clean_fifa_db.exec(
        select(FifaTeam).where(FifaTeam.league_id == la_liga.id)
    ).all()

    assert len(la_liga_teams) == 2
    team_names = {t.name for t in la_liga_teams}
    assert team_names == {"Real Madrid", "Barcelona"}

    # Verify league relationship
    for team in la_liga_teams:
        assert team.league_id == la_liga.id


def test_seed_fifa_data_overall_rating_calculation(
    clean_fifa_db: Session, sample_csv_file: Path
) -> None:
    """Test that overall_rating is computed correctly (att + mid + def)."""
    rows = seed_fifa_data.parse_csv(sample_csv_file)
    seed_fifa_data.seed_fifa_data(clean_fifa_db, rows)

    # Check Real Madrid: 90 + 88 + 85 = 263
    real_madrid = clean_fifa_db.exec(
        select(FifaTeam).where(FifaTeam.name == "Real Madrid")
    ).first()
    assert real_madrid is not None
    assert real_madrid.overall_rating == 263

    # Check Barcelona: 89 + 87 + 84 = 260
    barcelona = clean_fifa_db.exec(
        select(FifaTeam).where(FifaTeam.name == "Barcelona")
    ).first()
    assert barcelona is not None
    assert barcelona.overall_rating == 260

    # Check Manchester City: 91 + 89 + 86 = 266
    man_city = clean_fifa_db.exec(
        select(FifaTeam).where(FifaTeam.name == "Manchester City")
    ).first()
    assert man_city is not None
    assert man_city.overall_rating == 266


def test_seed_fifa_data_idempotency(
    clean_fifa_db: Session, sample_csv_file: Path
) -> None:
    """Test that running import twice is safe (no duplicates)."""
    rows = seed_fifa_data.parse_csv(sample_csv_file)

    # First import
    stats1 = seed_fifa_data.seed_fifa_data(clean_fifa_db, rows)
    assert stats1["leagues_created"] == 3
    assert stats1["leagues_skipped"] == 0
    assert stats1["teams_created"] == 6
    assert stats1["teams_skipped"] == 0

    # Count after first import
    leagues_after_first = len(clean_fifa_db.exec(select(FifaLeague)).all())
    teams_after_first = len(clean_fifa_db.exec(select(FifaTeam)).all())
    assert leagues_after_first == 3
    assert teams_after_first == 6

    # Second import (should skip everything)
    stats2 = seed_fifa_data.seed_fifa_data(clean_fifa_db, rows)
    assert stats2["leagues_created"] == 0
    assert stats2["leagues_skipped"] == 3
    assert stats2["teams_created"] == 0
    assert stats2["teams_skipped"] == 6

    # Count after second import (should be the same)
    leagues_after_second = len(clean_fifa_db.exec(select(FifaLeague)).all())
    teams_after_second = len(clean_fifa_db.exec(select(FifaTeam)).all())
    assert leagues_after_second == leagues_after_first
    assert teams_after_second == teams_after_first


def test_parse_csv_lowercase_short_headers(tmp_path: Path) -> None:
    """Test that CSV with lowercase short headers (team,league,att,mid,def) is accepted."""
    csv_file = tmp_path / "short_headers.csv"
    csv_file.write_text(
        "team,league,att,mid,def\n"
        "Real Madrid,La Liga,90,88,85\n"
        "Barcelona,La Liga,89,87,84\n"
    )

    rows = seed_fifa_data.parse_csv(csv_file)

    assert len(rows) == 2
    assert rows[0]["team_name"] == "Real Madrid"
    assert rows[0]["league_name"] == "La Liga"
    assert rows[0]["attack_rating"] == 90
    assert rows[0]["midfield_rating"] == 88
    assert rows[0]["defense_rating"] == 85
    # Country falls back to league name when no country column
    assert rows[0]["country"] == "La Liga"


def test_parse_csv_lowercase_short_headers_missing_column(tmp_path: Path) -> None:
    """Test that lowercase CSV with missing required column raises ValueError."""
    csv_file = tmp_path / "short_missing.csv"
    csv_file.write_text("team,league,att,mid\nTeam A,League X,80,80\n")

    with pytest.raises(ValueError, match="CSV missing required columns"):
        seed_fifa_data.parse_csv(csv_file)


def test_parse_csv_lowercase_short_headers_overall_rating(
    clean_fifa_db: Session, tmp_path: Path
) -> None:
    """Test overall_rating computed correctly from lowercase short-header CSV."""
    csv_file = tmp_path / "short_rating.csv"
    csv_file.write_text("team,league,att,mid,def\nTest Team,Test League,80,75,70\n")

    rows = seed_fifa_data.parse_csv(csv_file)
    stats = seed_fifa_data.seed_fifa_data(clean_fifa_db, rows)

    assert stats["teams_created"] == 1
    team = clean_fifa_db.exec(
        select(FifaTeam).where(FifaTeam.name == "Test Team")
    ).first()
    assert team is not None
    assert team.overall_rating == 225  # 80 + 75 + 70


def test_seed_fifa_data_team_deduplication_same_name_different_league(
    clean_fifa_db: Session, tmp_path: Path
) -> None:
    """Test that teams with same name in different leagues are both created."""
    csv_content = """Country,Team,League,Attack,Midfield,Defence
Spain,Athletic Club,La Liga,80,78,76
England,Athletic Club,Premier League,82,80,78
"""
    csv_file = tmp_path / "same_name_teams.csv"
    csv_file.write_text(csv_content)

    rows = seed_fifa_data.parse_csv(csv_file)
    stats = seed_fifa_data.seed_fifa_data(clean_fifa_db, rows)

    # Both teams should be created (different leagues)
    assert stats["teams_created"] == 2
    assert stats["teams_skipped"] == 0

    teams = clean_fifa_db.exec(
        select(FifaTeam).where(FifaTeam.name == "Athletic Club")
    ).all()
    assert len(teams) == 2

    # Verify they're in different leagues
    league_ids = {t.league_id for t in teams}
    assert len(league_ids) == 2
