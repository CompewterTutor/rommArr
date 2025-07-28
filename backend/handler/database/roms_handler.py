import functools
from collections.abc import Iterable, Sequence

from config import ROMM_DB_DRIVER
from decorators.database import begin_session
from models.collection import Collection, VirtualCollection
from models.platform import Platform
from models.rom import Rom, RomFile, RomMetadata, RomUser
from sqlalchemy import (
    Integer,
    Row,
    String,
    Text,
    and_,
    case,
    cast,
    delete,
    false,
    func,
    literal,
    not_,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.orm import InstrumentedAttribute, Query, Session, selectinload

from .base_handler import DBBaseHandler

EJS_SUPPORTED_PLATFORMS = [
    "3do",
    "64dd",
    "amiga",
    "amiga-cd",
    "amiga-cd32",
    "arcade",
    "neogeoaes",
    "neogeomvs",
    "atari2600",
    "atari-2600-plus",
    "atari5200",
    "atari7800",
    "c-plus-4",
    "c64",
    "cpet",
    "commodore-64c",
    "c128",
    "commmodore-128",
    "colecovision",
    "jaguar",
    "lynx",
    "atari-lynx-mkii",
    "neo-geo-pocket",
    "neo-geo-pocket-color",
    "nes",
    "famicom",
    "fds",
    "game-televisison",
    "new-style-nes",
    "n64",
    "ique-player",
    "nds",
    "nintendo-ds-lite",
    "nintendo-dsi",
    "nintendo-dsi-xl",
    "gb",
    "game-boy-pocket",
    "game-boy-light",
    "gba",
    "game-boy-adavance-sp",
    "game-boy-micro",
    "gbc",
    "pc-fx",
    "ps",
    "psp",
    "segacd",
    "sega32",
    "gamegear",
    "sms",
    "sega-mark-iii",
    "sega-game-box-9",
    "sega-master-system-ii",
    "master-system-super-compact",
    "master-system-girl",
    "genesis-slash-megadrive",
    "sega-mega-drive-2-slash-genesis",
    "sega-mega-jet",
    "mega-pc",
    "tera-drive",
    "sega-nomad",
    "saturn",
    "snes",
    "sfam",
    "super-nintendo-original-european-version",
    "super-famicom-shvc-001",
    "super-famicom-jr-model-shvc-101",
    "new-style-super-nes-model-sns-101",
    "turbografx16--1",
    "vic-20",
    "virtualboy",
    "wonderswan",
    "swancrystal",
    "wonderswan-color",
]


def with_details(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        kwargs["query"] = select(Rom).options(
            selectinload(Rom.saves),
            selectinload(Rom.states),
            selectinload(Rom.screenshots),
            selectinload(Rom.rom_users),
            selectinload(Rom.sibling_roms),
            selectinload(Rom.metadatum),
            selectinload(Rom.files),
            selectinload(Rom.collections),
        )
        return func(*args, **kwargs)

    return wrapper


def with_simple(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        kwargs["query"] = select(Rom).options(
            selectinload(Rom.rom_users),
            selectinload(Rom.metadatum),
            selectinload(Rom.files),
        )
        return func(*args, **kwargs)

    return wrapper


class DBRomsHandler(DBBaseHandler):
    @begin_session
    @with_details
    def add_rom(self, rom: Rom, query: Query = None, session: Session = None) -> Rom:
        rom = session.merge(rom)
        session.flush()

        return session.scalar(query.filter_by(id=rom.id).limit(1))

    @begin_session
    @with_details
    def get_rom(
        self, id: int, *, query: Query = None, session: Session = None
    ) -> Rom | None:
        return session.scalar(query.filter_by(id=id).limit(1))

    def filter_by_platform_id(self, query: Query, platform_id: int):
        return query.filter(Rom.platform_id == platform_id)

    def filter_by_collection_id(
        self, query: Query, session: Session, collection_id: int
    ):
        collection = (
            session.query(Collection)
            .filter(Collection.id == collection_id)
            .one_or_none()
        )
        if collection:
            return query.filter(Rom.id.in_(collection.rom_ids))
        return query

    def filter_by_virtual_collection_id(
        self, query: Query, session: Session, virtual_collection_id: str
    ):
        name, type = VirtualCollection.from_id(virtual_collection_id)
        v_collection = (
            session.query(VirtualCollection)
            .filter(VirtualCollection.name == name, VirtualCollection.type == type)
            .one_or_none()
        )
        if v_collection:
            return query.filter(Rom.id.in_(v_collection.rom_ids))
        return query

    def filter_by_search_term(self, query: Query, search_term: str):
        return query.filter(
            or_(
                Rom.fs_name.ilike(f"%{search_term}%"),
                Rom.name.ilike(f"%{search_term}%"),
            )
        )

    def filter_by_matched(self, query: Query, value: bool) -> Query:
        """Filter based on whether the rom is matched to a metadata provider."""
        predicate = or_(
            Rom.igdb_id.isnot(None),
            Rom.moby_id.isnot(None),
            Rom.ss_id.isnot(None),
            Rom.ra_id.isnot(None),
            Rom.launchbox_id.isnot(None),
            Rom.hasheous_id.isnot(None),
        )
        if not value:
            predicate = not_(predicate)
        return query.filter(predicate)

    def filter_by_favourite(
        self, query: Query, session: Session, value: bool, user_id: int | None
    ) -> Query:
        """Filter based on whether the rom is in the user's Favourites collection."""
        favourites_collection = (
            session.query(Collection)
            .filter(Collection.name.ilike("favourites"))
            .filter(Collection.user_id == user_id)
            .one_or_none()
        )

        if favourites_collection:
            predicate = Rom.id.in_(favourites_collection.rom_ids)
            if not value:
                predicate = not_(predicate)
            return query.filter(predicate)

        # If no Favourites collection exists, return the original query if non-favourites
        # were requested, or an empty query if favourites were requested.
        if not value:
            return query
        return query.filter(false())

    def filter_by_duplicate(self, query: Query, value: bool) -> Query:
        """Filter based on whether the rom has duplicates."""
        predicate = Rom.sibling_roms.any()
        if not value:
            predicate = not_(predicate)
        return query.filter(predicate)

    def filter_by_playable(self, query: Query, value: bool) -> Query:
        """Filter based on whether the rom is playable on supported platforms."""
        predicate = Platform.slug.in_(EJS_SUPPORTED_PLATFORMS)
        if not value:
            predicate = not_(predicate)
        return query.join(Rom.platform).filter(predicate)

    def filter_by_has_ra(self, query: Query, value: bool) -> Query:
        predicate = Rom.ra_id.isnot(None)
        if not value:
            predicate = not_(predicate)
        return query.filter(predicate)

    def filter_by_missing_from_fs(self, query: Query, value: bool) -> Query:
        predicate = Rom.missing_from_fs.isnot(False)
        if not value:
            predicate = not_(predicate)
        return query.filter(predicate)

    def filter_by_verified(self, query: Query):
        keys_to_check = [
            "tosec_match",
            "mame_arcade_match",
            "mame_mess_match",
            "nointro_match",
            "redump_match",
            "whdload_match",
            "ra_match",
            "fbneo_match",
        ]

        if ROMM_DB_DRIVER == "postgresql":
            conditions = " OR ".join(
                f"(hasheous_metadata->>'{key}')::boolean" for key in keys_to_check
            )
            return query.filter(text(conditions))
        else:
            return query.filter(
                or_(*(Rom.hasheous_metadata[key].as_boolean() for key in keys_to_check))
            )

    def filter_by_genre(self, query: Query, selected_genre: str):
        if ROMM_DB_DRIVER == "postgresql":
            return query.filter(
                text("genres @> (:genre)::jsonb").bindparams(
                    genre=f'["{selected_genre}"]'
                )
            )
        else:
            return query.filter(
                text("JSON_OVERLAPS(genres, JSON_ARRAY(:genre))").bindparams(
                    genre=selected_genre
                )
            )

    def filter_by_franchise(self, query: Query, selected_franchise: str):
        if ROMM_DB_DRIVER == "postgresql":
            return query.filter(
                text("franchises @> (:franchise)::jsonb").bindparams(
                    franchise=f'["{selected_franchise}"]'
                )
            )
        else:
            return query.filter(
                text("JSON_OVERLAPS(franchises, JSON_ARRAY(:franchise))").bindparams(
                    franchise=selected_franchise
                )
            )

    def filter_by_collection(self, query: Query, selected_collection: str):
        if ROMM_DB_DRIVER == "postgresql":
            return query.filter(
                text("collections @> (:collection)::jsonb").bindparams(
                    collection=f'["{selected_collection}"]'
                )
            )
        else:
            return query.filter(
                text("JSON_OVERLAPS(collections, JSON_ARRAY(:collection))").bindparams(
                    collection=selected_collection
                )
            )

    def filter_by_company(self, query: Query, selected_company: str):
        if ROMM_DB_DRIVER == "postgresql":
            return query.filter(
                text("companies @> (:company)::jsonb").bindparams(
                    company=f'["{selected_company}"]'
                )
            )
        else:
            return query.filter(
                text("JSON_OVERLAPS(companies, JSON_ARRAY(:company))").bindparams(
                    company=selected_company
                )
            )

    def filter_by_age_rating(self, query: Query, selected_age_rating: str):
        if ROMM_DB_DRIVER == "postgresql":
            return query.filter(
                text("age_ratings @> (:age_rating)::jsonb").bindparams(
                    age_rating=f'["{selected_age_rating}"]'
                )
            )
        else:
            return query.filter(
                text("JSON_OVERLAPS(age_ratings, JSON_ARRAY(:age_rating))").bindparams(
                    age_rating=selected_age_rating
                )
            )

    def filter_by_status(self, query: Query, selected_status: str):
        status_filter = RomUser.status == selected_status
        if selected_status == "now_playing":
            status_filter = RomUser.now_playing.is_(True)
        elif selected_status == "backlogged":
            status_filter = RomUser.backlogged.is_(True)
        elif selected_status == "hidden":
            status_filter = RomUser.hidden.is_(True)

        if selected_status == "hidden":
            return query.filter(status_filter)

        return query.filter(status_filter, RomUser.hidden.is_(False))

    def filter_by_region(self, query: Query, selected_region: str):
        if ROMM_DB_DRIVER == "postgresql":
            return query.filter(
                text("regions @> (:region)::jsonb").bindparams(
                    region=f'["{selected_region}"]'
                )
            )
        else:
            return query.filter(
                text("JSON_OVERLAPS(regions, JSON_ARRAY(:region))").bindparams(
                    region=selected_region
                )
            )

    def filter_by_language(self, query: Query, selected_language: str):
        if ROMM_DB_DRIVER == "postgresql":
            return query.filter(
                text("languages @> (:language)::jsonb").bindparams(
                    language=f'["{selected_language}"]'
                )
            )
        else:
            return query.filter(
                text("JSON_OVERLAPS(languages, JSON_ARRAY(:language))").bindparams(
                    language=selected_language
                )
            )

    @begin_session
    def filter_roms(
        self,
        query: Query,
        platform_id: int | None = None,
        collection_id: int | None = None,
        virtual_collection_id: str | None = None,
        search_term: str | None = None,
        matched: bool | None = None,
        favourite: bool | None = None,
        duplicate: bool | None = None,
        playable: bool | None = None,
        has_ra: bool | None = None,
        missing: bool | None = None,
        verified: bool | None = None,
        group_by_meta_id: bool = False,
        selected_genre: str | None = None,
        selected_franchise: str | None = None,
        selected_collection: str | None = None,
        selected_company: str | None = None,
        selected_age_rating: str | None = None,
        selected_status: str | None = None,
        selected_region: str | None = None,
        selected_language: str | None = None,
        user_id: int | None = None,
        session: Session = None,
    ) -> Query[Rom]:
        if platform_id:
            query = self.filter_by_platform_id(query, platform_id)

        if collection_id:
            query = self.filter_by_collection_id(query, session, collection_id)

        if virtual_collection_id:
            query = self.filter_by_virtual_collection_id(
                query, session, virtual_collection_id
            )

        if search_term:
            query = self.filter_by_search_term(query, search_term)

        if matched is not None:
            query = self.filter_by_matched(query, value=matched)

        if favourite is not None:
            query = self.filter_by_favourite(
                query, session=session, value=favourite, user_id=user_id
            )

        if duplicate is not None:
            query = self.filter_by_duplicate(query, value=duplicate)

        if playable is not None:
            query = self.filter_by_playable(query, value=playable)

        if has_ra is not None:
            query = self.filter_by_has_ra(query, value=has_ra)

        if missing is not None:
            query = self.filter_by_missing_from_fs(query, value=missing)

        # TODO: Correctly support true/false values.
        if verified:
            query = self.filter_by_verified(query)

        if group_by_meta_id:

            def build_func(provider: str, column: InstrumentedAttribute):
                if platform_id:
                    return func.concat(provider, "-", Rom.platform_id, "-", column)

                return func.concat(provider, "-", Rom.platform_id, "-", column)

            group_id = case(
                {
                    Rom.igdb_id.isnot(None): build_func("igdb", Rom.igdb_id),
                    Rom.moby_id.isnot(None): build_func("moby", Rom.moby_id),
                    Rom.ss_id.isnot(None): build_func("ss", Rom.ss_id),
                    Rom.launchbox_id.isnot(None): build_func(
                        "launchbox", Rom.launchbox_id
                    ),
                },
                else_=build_func("romm", Rom.id),
            )

            # Convert NULL is_main_sibling to 0 (false) so it sorts after true values
            is_main_sibling_order = (
                func.coalesce(cast(RomUser.is_main_sibling, Integer), 0).desc()
                if user_id
                else literal(1)
            )

            # Create a subquery that identifies the first ROM in each group
            group_subquery = (
                session.query(Rom.id)
                .outerjoin(
                    RomUser, and_(RomUser.rom_id == Rom.id, RomUser.user_id == user_id)
                )
                .add_columns(
                    group_id.label("group_id"),
                    func.row_number()
                    .over(
                        partition_by=group_id,
                        order_by=[is_main_sibling_order, Rom.fs_name_no_ext],
                    )
                    .label("row_num"),
                )
                .subquery()
            )

            # Add a filter to the original query to only include the first ROM from each group
            query = query.filter(
                Rom.id.in_(
                    session.query(group_subquery.c.id).filter(
                        group_subquery.c.row_num == 1
                    )
                )
            )

        if (
            selected_genre
            or selected_franchise
            or selected_collection
            or selected_company
            or selected_age_rating
        ):
            query = query.join(RomMetadata)

        if selected_genre:
            query = self.filter_by_genre(query, selected_genre)

        if selected_franchise:
            query = self.filter_by_franchise(query, selected_franchise)

        if selected_collection:
            query = self.filter_by_collection(query, selected_collection)

        if selected_company:
            query = self.filter_by_company(query, selected_company)

        if selected_age_rating:
            query = self.filter_by_age_rating(query, selected_age_rating)

        if selected_region:
            query = self.filter_by_region(query, selected_region)

        if selected_language:
            query = self.filter_by_language(query, selected_language)

        # The RomUser table is already joined if user_id is set
        if selected_status and user_id:
            query = self.filter_by_status(query, selected_status)
        elif user_id:
            query = query.filter(
                or_(RomUser.hidden.is_(False), RomUser.hidden.is_(None))
            )

        return query

    @with_simple
    @begin_session
    def get_roms_query(
        self,
        *,
        order_by: str = "name",
        order_dir: str = "asc",
        user_id: int | None = None,
        query: Query = None,
        session: Session = None,
    ) -> Query[Rom]:
        if user_id:
            query = query.outerjoin(
                RomUser, and_(RomUser.rom_id == Rom.id, RomUser.user_id == user_id)
            )

        if user_id and hasattr(RomUser, order_by) and not hasattr(Rom, order_by):
            order_attr = getattr(RomUser, order_by)
            query = query.filter(RomUser.user_id == user_id, order_attr.isnot(None))
        elif hasattr(RomMetadata, order_by) and not hasattr(Rom, order_by):
            order_attr = getattr(RomMetadata, order_by)
            query = query.outerjoin(RomMetadata, RomMetadata.rom_id == Rom.id).filter(
                order_attr.isnot(None)
            )
        elif hasattr(Rom, order_by):
            order_attr = getattr(Rom, order_by)
        else:
            order_attr = Rom.name

        # Handle computed properties
        if order_by == "fs_size_bytes":
            subquery = (
                session.query(
                    RomFile.rom_id,
                    func.sum(RomFile.file_size_bytes).label("total_size"),
                )
                .group_by(RomFile.rom_id)
                .subquery()
            )
            query = query.outerjoin(subquery, Rom.id == subquery.c.rom_id)
            order_attr = func.coalesce(subquery.c.total_size, 0)

        # Ignore case when the order attribute is a number
        if isinstance(order_attr.type, (String, Text)):
            # Remove any leading articles
            order_attr = func.trim(
                func.lower(order_attr).regexp_replace(r"^(the|a|an)\s+", "", "i")
            )

        if order_dir.lower() == "desc":
            order_attr = order_attr.desc()
        else:
            order_attr = order_attr.asc()

        return query.order_by(order_attr)

    @begin_session
    def get_roms_scalar(
        self,
        *,
        session: Session = None,
        **kwargs,
    ) -> Sequence[Rom]:
        query = self.get_roms_query(
            order_by=kwargs.pop("order_by", "name"),
            order_dir=kwargs.pop("order_dir", "asc"),
            user_id=kwargs.pop("user_id", None),
        )
        roms = self.filter_roms(
            query=query,
            platform_id=kwargs.pop("platform_id", None),
            collection_id=kwargs.pop("collection_id", None),
            virtual_collection_id=kwargs.pop("virtual_collection_id", None),
            search_term=kwargs.pop("search_term", None),
            matched=kwargs.pop("matched", None),
            favourite=kwargs.pop("favourite", None),
            duplicate=kwargs.pop("duplicate", None),
            playable=kwargs.pop("playable", None),
            has_ra=kwargs.pop("has_ra", None),
            missing=kwargs.pop("missing", None),
            verified=kwargs.pop("verified", None),
            selected_genre=kwargs.pop("selected_genre", None),
            selected_franchise=kwargs.pop("selected_franchise", None),
            selected_collection=kwargs.pop("selected_collection", None),
            selected_company=kwargs.pop("selected_company", None),
            selected_age_rating=kwargs.pop("selected_age_rating", None),
            selected_status=kwargs.pop("selected_status", None),
            selected_region=kwargs.pop("selected_region", None),
            selected_language=kwargs.pop("selected_language", None),
            user_id=kwargs.pop("user_id", None),
        )
        return session.scalars(roms).all()

    @begin_session
    def get_char_index(
        self, query: Query, session: Session = None
    ) -> list[Row[tuple[str, int]]]:
        # Get the row number and first letter for each item
        subquery = query.add_columns(
            func.lower(func.substring(Rom.name, 1, 1)).label("letter"),
            func.row_number().over(order_by=Rom.name).label("position"),
        ).subquery()

        # Get the minimum position for each letter
        return (
            session.query(
                subquery.c.letter, func.min(subquery.c.position - 1).label("position")
            )
            .group_by(subquery.c.letter)
            .order_by(subquery.c.letter)
            .all()
        )

    @begin_session
    @with_details
    def get_roms_by_fs_name(
        self,
        platform_id: int,
        fs_names: Iterable[str],
        query: Query = None,
        session: Session = None,
    ) -> dict[str, Rom]:
        """Retrieve a dictionary of roms by their filesystem names."""
        roms = (
            session.scalars(
                query.filter(Rom.fs_name.in_(fs_names)).filter_by(
                    platform_id=platform_id
                )
            )
            .unique()
            .all()
        )
        return {rom.fs_name: rom for rom in roms}

    @begin_session
    def update_rom(self, id: int, data: dict, session: Session = None) -> Rom:
        session.execute(
            update(Rom)
            .where(Rom.id == id)
            .values(**data)
            .execution_options(synchronize_session="evaluate")
        )
        return session.query(Rom).filter_by(id=id).one()

    @begin_session
    def delete_rom(self, id: int, session: Session = None) -> None:
        session.execute(
            delete(Rom)
            .where(Rom.id == id)
            .execution_options(synchronize_session="evaluate")
        )

    @begin_session
    def mark_missing_roms(
        self, platform_id: int, fs_roms_to_keep: list[str], session: Session = None
    ) -> Sequence[Rom]:
        missing_roms = (
            session.scalars(
                select(Rom)
                .order_by(Rom.fs_name.asc())
                .where(
                    and_(
                        Rom.platform_id == platform_id,
                        Rom.fs_name.not_in(fs_roms_to_keep),
                    )
                )
            )
            .unique()
            .all()
        )
        session.execute(
            update(Rom)
            .where(
                and_(
                    Rom.platform_id == platform_id, Rom.fs_name.not_in(fs_roms_to_keep)
                )
            )
            .values(**{"missing_from_fs": True})
            .execution_options(synchronize_session="evaluate")
        )
        return missing_roms

    @begin_session
    def add_rom_user(
        self, rom_id: int, user_id: int, session: Session = None
    ) -> RomUser:
        return session.merge(RomUser(rom_id=rom_id, user_id=user_id))

    @begin_session
    def get_rom_user(
        self, rom_id: int, user_id: int, session: Session = None
    ) -> RomUser | None:
        return session.scalar(
            select(RomUser).filter_by(rom_id=rom_id, user_id=user_id).limit(1)
        )

    @begin_session
    def get_rom_user_by_id(self, id: int, session: Session = None) -> RomUser | None:
        return session.scalar(select(RomUser).filter_by(id=id).limit(1))

    @begin_session
    def update_rom_user(
        self, id: int, data: dict, session: Session = None
    ) -> RomUser | None:
        session.execute(
            update(RomUser)
            .where(RomUser.id == id)
            .values(**data)
            .execution_options(synchronize_session="evaluate")
        )

        rom_user = self.get_rom_user_by_id(id)
        if not rom_user:
            return None

        if not data.get("is_main_sibling", False):
            return rom_user

        rom = self.get_rom(rom_user.rom_id)
        if not rom:
            return rom_user

        session.execute(
            update(RomUser)
            .where(
                and_(
                    RomUser.rom_id.in_(r.id for r in rom.sibling_roms),
                    RomUser.user_id == rom_user.user_id,
                )
            )
            .values(is_main_sibling=False)
        )

        return session.query(RomUser).filter_by(id=id).one()

    @begin_session
    def add_rom_file(self, rom_file: RomFile, session: Session = None) -> RomFile:
        return session.merge(rom_file)

    @begin_session
    def get_rom_file_by_id(self, id: int, session: Session = None) -> RomFile | None:
        return session.scalar(select(RomFile).filter_by(id=id).limit(1))

    @begin_session
    def update_rom_file(self, id: int, data: dict, session: Session = None) -> RomFile:
        session.execute(
            update(RomFile)
            .where(RomFile.id == id)
            .values(**data)
            .execution_options(synchronize_session="evaluate")
        )

        return session.query(RomFile).filter_by(id=id).one()

    @begin_session
    def purge_rom_files(
        self, rom_id: int, session: Session = None
    ) -> Sequence[RomFile]:
        purged_rom_files = (
            session.scalars(select(RomFile).filter_by(rom_id=rom_id)).unique().all()
        )
        session.execute(
            delete(RomFile)
            .where(RomFile.rom_id == rom_id)
            .execution_options(synchronize_session="evaluate")
        )
        return purged_rom_files
