"""Tests for database models and session management."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from idealista_scraper.db import (
    Base,
    Concelho,
    District,
    Listing,
    ListingHistory,
    ScrapeRun,
)


def get_test_session() -> sessionmaker:
    """Create an in-memory SQLite database session factory for testing.

    Returns:
        A sessionmaker instance configured with an in-memory database.
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


class TestDatabaseSetup:
    """Tests for database initialization."""

    def test_create_tables(self) -> None:
        """Test that all tables can be created."""
        session_factory = get_test_session()
        session = session_factory()

        # Verify tables exist by querying them
        session.query(District).count()
        session.query(Concelho).count()
        session.query(Listing).count()
        session.query(ListingHistory).count()
        session.query(ScrapeRun).count()

        session.close()


class TestDistrictModel:
    """Tests for the District model."""

    def test_create_district(self) -> None:
        """Test creating a district."""
        session_factory = get_test_session()
        session = session_factory()

        district = District(
            name="Lisboa",
            slug="lisboa-distrito",
            listing_count=50000,
        )
        session.add(district)
        session.commit()

        # Query back
        result = session.query(District).filter_by(slug="lisboa-distrito").first()
        assert result is not None
        assert result.name == "Lisboa"
        assert result.slug == "lisboa-distrito"
        assert result.listing_count == 50000
        assert result.created_at is not None

        session.close()

    def test_district_repr(self) -> None:
        """Test district string representation."""
        district = District(id=1, name="Lisboa", slug="lisboa-distrito")
        repr_str = repr(district)

        assert "District" in repr_str
        assert "Lisboa" in repr_str
        assert "lisboa-distrito" in repr_str


class TestConcelhoModel:
    """Tests for the Concelho model."""

    def test_create_concelho_with_district(self) -> None:
        """Test creating a concelho with a parent district."""
        session_factory = get_test_session()
        session = session_factory()

        district = District(name="Lisboa", slug="lisboa-distrito")
        session.add(district)
        session.flush()

        concelho = Concelho(
            district_id=district.id,
            name="Cascais",
            slug="cascais",
            listing_count=5000,
        )
        session.add(concelho)
        session.commit()

        # Query back
        result = session.query(Concelho).filter_by(slug="cascais").first()
        assert result is not None
        assert result.name == "Cascais"
        assert result.district_id == district.id
        assert result.district.name == "Lisboa"

        session.close()

    def test_district_concelho_relationship(self) -> None:
        """Test the district-concelho relationship."""
        session_factory = get_test_session()
        session = session_factory()

        district = District(name="Lisboa", slug="lisboa-distrito")
        session.add(district)
        session.flush()

        # Add multiple concelhos
        concelho1 = Concelho(district_id=district.id, name="Cascais", slug="cascais")
        concelho2 = Concelho(district_id=district.id, name="Sintra", slug="sintra")
        session.add_all([concelho1, concelho2])
        session.commit()

        # Access concelhos via district
        result = session.query(District).filter_by(slug="lisboa-distrito").first()
        assert result is not None
        assert len(result.concelhos) == 2
        concelho_names = [c.name for c in result.concelhos]
        assert "Cascais" in concelho_names
        assert "Sintra" in concelho_names

        session.close()


class TestListingModel:
    """Tests for the Listing model."""

    def test_create_listing(self) -> None:
        """Test creating a listing."""
        session_factory = get_test_session()
        session = session_factory()

        district = District(name="Lisboa", slug="lisboa-distrito")
        session.add(district)
        session.flush()

        concelho = Concelho(district_id=district.id, name="Cascais", slug="cascais")
        session.add(concelho)
        session.flush()

        listing = Listing(
            idealista_id=12345678,
            concelho_id=concelho.id,
            operation="comprar",
            property_type="casas",
            url="https://www.idealista.pt/imovel/12345678/",
            title="Moradia T5 em Cascais",
            price=1500000,
            typology="T5",
            bedrooms=5,
            bathrooms=4,
            area_gross=350.0,
            is_active=True,
        )
        session.add(listing)
        session.commit()

        # Query back
        result = session.query(Listing).filter_by(idealista_id=12345678).first()
        assert result is not None
        assert result.title == "Moradia T5 em Cascais"
        assert result.price == 1500000
        assert result.typology == "T5"
        assert result.concelho.name == "Cascais"

        session.close()

    def test_listing_with_all_fields(self) -> None:
        """Test creating a listing with all fields populated."""
        session_factory = get_test_session()
        session = session_factory()

        district = District(name="Lisboa", slug="lisboa-distrito")
        session.add(district)
        session.flush()

        concelho = Concelho(district_id=district.id, name="Cascais", slug="cascais")
        session.add(concelho)
        session.flush()

        now = datetime.now(UTC)
        listing = Listing(
            idealista_id=12345678,
            concelho_id=concelho.id,
            operation="comprar",
            property_type="casas",
            url="https://www.idealista.pt/imovel/12345678/",
            title="Moradia T5 em Cascais",
            price=1500000,
            price_per_sqm=4285.71,
            typology="T5",
            bedrooms=5,
            bathrooms=4,
            area_gross=350.0,
            area_useful=300.0,
            floor="2º andar",
            has_elevator=True,
            has_garage=True,
            has_pool=True,
            has_garden=True,
            has_terrace=False,
            has_balcony=True,
            has_air_conditioning=True,
            has_central_heating=True,
            is_luxury=True,
            has_sea_view=False,
            energy_class="B",
            condition="Segunda mão/bom estado",
            year_built=2015,
            street="Rua das Flores, 123",
            neighborhood="Centro",
            parish="Cascais",
            description="Fantástica moradia de luxo",
            agency_name="RE/MAX Cascais",
            agency_url="/agencia/remax-cascais/",
            reference="ABC123",
            tags="Luxo,Piscina,Jardim",
            image_url="https://example.com/photo.jpg",
            first_seen=now,
            last_seen=now,
            is_active=True,
            raw_data={"source": "test"},
        )
        session.add(listing)
        session.commit()

        # Query back
        result = session.query(Listing).filter_by(idealista_id=12345678).first()
        assert result is not None
        assert result.has_pool is True
        assert result.has_sea_view is False
        assert result.energy_class == "B"
        assert result.year_built == 2015
        assert result.raw_data == {"source": "test"}

        session.close()


class TestListingHistoryModel:
    """Tests for the ListingHistory model."""

    def test_create_history_record(self) -> None:
        """Test creating a listing history record."""
        session_factory = get_test_session()
        session = session_factory()

        district = District(name="Lisboa", slug="lisboa-distrito")
        session.add(district)
        session.flush()

        concelho = Concelho(district_id=district.id, name="Cascais", slug="cascais")
        session.add(concelho)
        session.flush()

        listing = Listing(
            idealista_id=12345678,
            concelho_id=concelho.id,
            operation="comprar",
            property_type="casas",
            url="https://www.idealista.pt/imovel/12345678/",
            price=1500000,
        )
        session.add(listing)
        session.flush()

        history = ListingHistory(
            listing_id=listing.id,
            price=1600000,  # Old price before reduction
            changes={"price": {"old": 1600000, "new": 1500000}},
        )
        session.add(history)
        session.commit()

        # Query back
        result = session.query(ListingHistory).filter_by(listing_id=listing.id).first()
        assert result is not None
        assert result.price == 1600000
        assert result.changes["price"]["old"] == 1600000
        assert result.changes["price"]["new"] == 1500000

        session.close()

    def test_listing_history_relationship(self) -> None:
        """Test the listing-history relationship."""
        session_factory = get_test_session()
        session = session_factory()

        district = District(name="Lisboa", slug="lisboa-distrito")
        session.add(district)
        session.flush()

        concelho = Concelho(district_id=district.id, name="Cascais", slug="cascais")
        session.add(concelho)
        session.flush()

        listing = Listing(
            idealista_id=12345678,
            concelho_id=concelho.id,
            operation="comprar",
            property_type="casas",
            url="https://www.idealista.pt/imovel/12345678/",
            price=1400000,
        )
        session.add(listing)
        session.flush()

        # Add multiple history records
        history1 = ListingHistory(listing_id=listing.id, price=1600000)
        history2 = ListingHistory(listing_id=listing.id, price=1500000)
        session.add_all([history1, history2])
        session.commit()

        # Access history via listing
        result = session.query(Listing).filter_by(idealista_id=12345678).first()
        assert result is not None
        assert len(result.history) == 2
        prices = [h.price for h in result.history]
        assert 1600000 in prices
        assert 1500000 in prices

        session.close()


class TestScrapeRunModel:
    """Tests for the ScrapeRun model."""

    def test_create_scrape_run(self) -> None:
        """Test creating a scrape run."""
        session_factory = get_test_session()
        session = session_factory()

        now = datetime.now(UTC)
        run = ScrapeRun(
            run_type="scrape",
            status="running",
            started_at=now,
            config={"locations": ["cascais"], "operation": "comprar"},
        )
        session.add(run)
        session.commit()

        # Query back
        result = session.query(ScrapeRun).filter_by(run_type="scrape").first()
        assert result is not None
        assert result.status == "running"
        assert result.config["locations"] == ["cascais"]

        session.close()

    def test_update_scrape_run_status(self) -> None:
        """Test updating a scrape run status on completion."""
        session_factory = get_test_session()
        session = session_factory()

        now = datetime.now(UTC)
        run = ScrapeRun(
            run_type="scrape",
            status="running",
            started_at=now,
        )
        session.add(run)
        session.commit()

        # Update status
        run.status = "success"
        run.ended_at = datetime.now(UTC)
        run.listings_processed = 100
        run.listings_created = 80
        run.listings_updated = 20
        session.commit()

        # Query back
        result = session.query(ScrapeRun).filter_by(id=run.id).first()
        assert result is not None
        assert result.status == "success"
        assert result.listings_processed == 100
        assert result.listings_created == 80
        assert result.listings_updated == 20
        assert result.ended_at is not None

        session.close()

    def test_scrape_run_with_error(self) -> None:
        """Test recording a failed scrape run."""
        session_factory = get_test_session()
        session = session_factory()

        now = datetime.now(UTC)
        run = ScrapeRun(
            run_type="scrape",
            status="failed",
            started_at=now,
            ended_at=now,
            error_message="Connection timeout",
        )
        session.add(run)
        session.commit()

        # Query back
        result = session.query(ScrapeRun).filter_by(status="failed").first()
        assert result is not None
        assert result.error_message == "Connection timeout"

        session.close()
