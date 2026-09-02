import asyncio
import typing as tp

import aiosqlite
from pypika import Column, Query, Table, queries

from entities.application import Application
from entities.herald import Herald
from entities.vote import Vote


class ProtoeuroBotDatabase:    
    def __init__(self, db_name: str):
        self.db_name = db_name
        self.connection = None
        self._write_lock = asyncio.Lock()

    async def connect(self):
        self.connection = await aiosqlite.connect(self.db_name)
        await self.connection.execute("PRAGMA foreign_keys = ON")

    async def execute_get_query(self, query: queries.QueryBuilder) -> tp.Sequence[tp.Any] | None:
        if self.connection is not None:
            cursor = await self.connection.execute(str(query))
            return await cursor.fetchall() # type: ignore
        return None

    async def execute_post_query(self, query: queries.QueryBuilder) -> None:
        if self.connection is not None:
            await self.connection.execute(str(query))
            await self.connection.commit()

    async def create_tables(self) -> None:
        q = Query.create_table('country_selections').columns(
            Column('country_name', "TEXT", nullable=False),
            Column('country_flag', "TEXT", nullable=False),
            Column('user_id', "INTEGER", nullable=False),
        ).primary_key('country_name').unique('user_id').if_not_exists()
        await self.execute_post_query(q) # type: ignore

        q = Query.create_table('applications').columns(
            Column('user_id', "INTEGER REFERENCES country_selections(user_id)", nullable=False),
            Column('singer_name', "TEXT", nullable=False),
            Column('song_name', "TEXT", nullable=False),
            Column('video_link', "TEXT", nullable=False),
            Column('video_start', "INTEGER", nullable=False),
            Column('video_end', "INTEGER", nullable=False),
            Column('singer_photo', "TEXT", nullable=False),
        ).primary_key('user_id').if_not_exists()
        await self.execute_post_query(q) # type: ignore

        q = Query.create_table("heralds").columns(
            Column("user_id", "INTEGER REFERENCES applications(user_id)", nullable=False),
            Column("herald_photo", "TEXT", nullable=False),
            Column("herald_text", "TEXT", nullable=False),
        ).primary_key("user_id").if_not_exists()
        await self.execute_post_query(q) # type: ignore
        
        q = Query.create_table("ballots").columns(
            Column("voter_user_id", "INTEGER REFERENCES applications(user_id)", nullable=False),
            Column("submitted_at", "TEXT", nullable=False),
        ).primary_key("voter_user_id").if_not_exists()
        await self.execute_post_query(q) # type: ignore

        q = Query.create_table("votes").columns(
            Column("voter_user_id", "INTEGER REFERENCES applications(user_id)", nullable=False),
            Column(
                "target_user_id",
                "INTEGER REFERENCES applications(user_id) CHECK (target_user_id != voter_user_id)",
                nullable=False,
            ),
            Column(
                "points",
                "INTEGER CHECK (points IN (12, 10, 8, 7, 6, 5, 4, 3, 2, 1))",
                nullable=False,
            ),
        ).primary_key("voter_user_id", "target_user_id").unique("voter_user_id", "points").if_not_exists()
        await self.execute_post_query(q) # type: ignore

        q = Query.create_table("bot_state").columns(
            Column("id", "INTEGER PRIMARY KEY CHECK (id = 1)", nullable=False),
            Column(
                "active_stage",
                "TEXT CHECK (active_stage IN ('applications_stage', 'finalize_applications', 'voting_stage', 'finalization_stage'))",
                nullable=False,
            ),
        ).if_not_exists()
        await self.execute_post_query(q) # type: ignore
        if self.connection is not None:
            await self.connection.execute(
                """
                INSERT OR IGNORE INTO bot_state (id, active_stage)
                VALUES (1, 'applications_stage')
                """
            )
            await self.connection.commit()

    async def teardown(self) -> None:
        if self.connection:
            await self.connection.close()

    async def get_active_stage(self) -> str:
        if self.connection is None:
            raise RuntimeError("Database is not connected.")

        cursor = await self.connection.execute(
            "SELECT active_stage FROM bot_state WHERE id = 1"
        )
        result = await cursor.fetchone()
        if result is None:
            raise RuntimeError("Bot stage is not initialized.")

        return result[0]

    async def _is_active_stage(self, expected_stage: str) -> bool:
        if self.connection is None:
            return False

        cursor = await self.connection.execute(
            "SELECT active_stage FROM bot_state WHERE id = 1"
        )
        result = await cursor.fetchone()
        return result is not None and result[0] == expected_stage

    async def transition_to_applications_finalization(self) -> bool:
        if self.connection is None:
            return False

        async with self._write_lock:
            cursor = await self.connection.execute(
                """
                UPDATE bot_state
                SET active_stage = 'finalize_applications'
                WHERE id = 1 AND active_stage = 'applications_stage'
                """
            )
            await self.connection.commit()
        return cursor.rowcount == 1

    async def transition_to_voting(self) -> bool:
        if self.connection is None:
            return False

        async with self._write_lock:
            cursor = await self.connection.execute(
                """
                UPDATE bot_state
                SET active_stage = 'voting_stage'
                WHERE id = 1 AND active_stage = 'finalize_applications'
                """
            )
            await self.connection.commit()
        return cursor.rowcount == 1

    async def transition_to_finalization(self) -> bool:
        if self.connection is None:
            return False

        async with self._write_lock:
            cursor = await self.connection.execute(
                """
                UPDATE bot_state
                SET active_stage = 'finalization_stage'
                WHERE id = 1 AND active_stage = 'voting_stage'
                """
            )
            await self.connection.commit()
        return cursor.rowcount == 1
    
    # application stage
    
    async def is_booked(self, country_name) -> bool:
        country_selections = Table("country_selections")
        q = Query.from_(country_selections).select("country_name").where(
            country_selections.country_name == country_name
        )
        result = await self.execute_get_query(q)
        return bool(result)

    async def get_selected_country(self, user_id: int) -> tuple[str, str] | None:
        country_selections = Table("country_selections")
        q = Query.from_(country_selections).select(
            "country_name",
            "country_flag",
        ).where(country_selections.user_id == user_id)
        result = await self.execute_get_query(q)
        if not result:
            return None

        country_name, country_flag = result[0]
        return country_name, country_flag
    
    async def book_country(self, user_id: int, country_name, country_flag) -> bool:
        if self.connection is None:
            return False

        country_selections = Table("country_selections")
        q = Query.into(country_selections).columns(
            "country_name",
            "country_flag",
            "user_id",
        ).insert(country_name, country_flag, user_id)

        async with self._write_lock:
            try:
                await self.connection.execute("BEGIN")
                if not await self._is_active_stage("applications_stage"):
                    await self.connection.rollback()
                    return False

                await self.connection.execute(str(q))
                await self.connection.commit()
            except aiosqlite.Error:
                await self.connection.rollback()
                return False

        return True
    
    async def booked_countries(self) -> list[str]:
        country_selections = Table("country_selections")
        q = Query.from_(country_selections).select("country_name").orderby(
            country_selections.country_name
        )
        result = await self.execute_get_query(q)
        if result is None:
            return []

        return [country_name for (country_name,) in result]

    async def get_country_selections(self) -> list[tuple[str, int]]:
        country_selections = Table("country_selections")
        q = Query.from_(country_selections).select(
            "country_name",
            "user_id",
        ).orderby(country_selections.country_name)
        result = await self.execute_get_query(q)
        if result is None:
            return []

        return [(country_name, user_id) for country_name, user_id in result]

    async def get_participant_user_ids(self) -> list[int]:
        country_selections = Table("country_selections")
        q = Query.from_(country_selections).select(
            country_selections.user_id
        ).orderby(country_selections.country_name)
        result = await self.execute_get_query(q)
        if result is None:
            return []

        return [user_id for (user_id,) in result]

    async def get_users_without_application(self) -> list[int]:
        country_selections = Table("country_selections")
        applications = Table("applications")
        q = Query.from_(country_selections).left_join(applications).on(
            country_selections.user_id == applications.user_id
        ).select(
            country_selections.user_id
        ).where(
            applications.user_id.isnull()
        ).orderby(country_selections.country_name)
        result = await self.execute_get_query(q)
        if result is None:
            return []

        return [user_id for (user_id,) in result]

    async def get_users_without_vote_or_herald(self) -> list[int]:
        applications = Table("applications")
        ballots = Table("ballots")
        heralds = Table("heralds")
        q = Query.from_(applications).left_join(ballots).on(
            applications.user_id == ballots.voter_user_id
        ).left_join(heralds).on(
            applications.user_id == heralds.user_id
        ).select(
            applications.user_id
        ).where(
            ballots.voter_user_id.isnull() | heralds.user_id.isnull()
        )
        result = await self.execute_get_query(q)
        if result is None:
            return []

        return [user_id for (user_id,) in result]

    async def has_application(self, user_id: int) -> bool:
        applications = Table("applications")
        q = Query.from_(applications).select("user_id").where(
            applications.user_id == user_id
        )
        result = await self.execute_get_query(q)
        return bool(result)

    async def get_application(self, user_id: int) -> Application | None:
        applications = Table("applications")
        country_selections = Table("country_selections")
        q = Query.from_(applications).join(country_selections).on(
            applications.user_id == country_selections.user_id
        ).select(
            applications.user_id,
            country_selections.country_name,
            country_selections.country_flag,
            applications.singer_name,
            applications.song_name,
            applications.video_link,
            applications.video_start,
            applications.video_end,
            applications.singer_photo,
        ).where(applications.user_id == user_id)
        result = await self.execute_get_query(q)
        if not result:
            return None

        return Application(*result[0])

    async def get_applications(self) -> list[Application]:
        applications = Table("applications")
        country_selections = Table("country_selections")
        q = Query.from_(applications).join(country_selections).on(
            applications.user_id == country_selections.user_id
        ).select(
            applications.user_id,
            country_selections.country_name,
            country_selections.country_flag,
            applications.singer_name,
            applications.song_name,
            applications.video_link,
            applications.video_start,
            applications.video_end,
            applications.singer_photo,
        ).orderby(country_selections.country_name)
        result = await self.execute_get_query(q)
        if result is None:
            return []

        return [Application(*row) for row in result]

    async def add_vote(self, voter_user_id: int, country_names: list[str]) -> bool:
        points = (12, 10, 8, 7, 6, 5, 4, 3, 2, 1)
        if self.connection is None or len(country_names) != len(points):
            return False
        if len(set(country_names)) != len(country_names):
            return False

        applications = Table("applications")
        country_selections = Table("country_selections")
        q = Query.from_(country_selections).join(applications).on(
            country_selections.user_id == applications.user_id
        ).select(
            country_selections.country_name,
            applications.user_id,
        ).where(country_selections.country_name.isin(country_names))
        result = await self.execute_get_query(q)
        if result is None or len(result) != len(country_names):
            return False

        target_ids = {country_name: user_id for country_name, user_id in result}
        vote_rows = [
            (voter_user_id, target_ids[country_name], points[index])
            for index, country_name in enumerate(country_names)
        ]

        async with self._write_lock:
            try:
                await self.connection.execute("BEGIN")
                if not await self._is_active_stage("voting_stage"):
                    await self.connection.rollback()
                    return False

                await self.connection.execute(
                    """
                    INSERT INTO ballots (voter_user_id, submitted_at)
                    VALUES (?, datetime('now'))
                    ON CONFLICT(voter_user_id) DO UPDATE SET
                        submitted_at = excluded.submitted_at
                    """,
                    (voter_user_id,),
                )
                await self.connection.execute(
                    "DELETE FROM votes WHERE voter_user_id = ?",
                    (voter_user_id,),
                )
                await self.connection.executemany(
                    "INSERT INTO votes (voter_user_id, target_user_id, points) VALUES (?, ?, ?)",
                    vote_rows,
                )
                await self.connection.commit()
            except aiosqlite.Error:
                await self.connection.rollback()
                return False

        return True

    async def add_herald(self, user_id: int, herald_photo: str, herald_text: str) -> bool:
        if self.connection is None:
            return False

        async with self._write_lock:
            try:
                await self.connection.execute("BEGIN")
                if not await self._is_active_stage("voting_stage"):
                    await self.connection.rollback()
                    return False

                await self.connection.execute(
                    """
                    INSERT INTO heralds (user_id, herald_photo, herald_text)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        herald_photo = excluded.herald_photo,
                        herald_text = excluded.herald_text
                    """,
                    (user_id, herald_photo, herald_text),
                )
                await self.connection.commit()
            except aiosqlite.Error:
                await self.connection.rollback()
                return False

        return True

    async def get_herald(self, user_id: int) -> Herald | None:
        heralds = Table("heralds")
        q = Query.from_(heralds).select(
            "herald_photo",
            "herald_text",
        ).where(heralds.user_id == user_id)
        result = await self.execute_get_query(q)
        if not result:
            return None

        return Herald(*result[0])
    
    async def get_vote(self, voter_user_id: int) -> Vote | None:
        votes = Table("votes")
        target_countries = Table("country_selections").as_("target_countries")
        voter_countries = Table("country_selections").as_("voter_countries")
        q = Query.from_(votes).join(target_countries).on(
            votes.target_user_id == target_countries.user_id
        ).join(voter_countries).on(
            votes.voter_user_id == voter_countries.user_id
        ).select(
            voter_countries.country_name,
            votes.points,
            target_countries.country_name,
        ).where(votes.voter_user_id == voter_user_id)
        result = await self.execute_get_query(q)
        if not result:
            return None

        voter_country_name = result[0][0]
        countries_by_points = {
            points: country_name
            for _, points, country_name in result
        }
        required_points = (12, 10, 8, 7, 6, 5, 4, 3, 2, 1)
        if set(countries_by_points) != set(required_points):
            return None

        return Vote(
            user_id=voter_user_id,
            country_name=voter_country_name,
            p_12=countries_by_points[12],
            p_10=countries_by_points[10],
            p_8=countries_by_points[8],
            p_7=countries_by_points[7],
            p_6=countries_by_points[6],
            p_5=countries_by_points[5],
            p_4=countries_by_points[4],
            p_3=countries_by_points[3],
            p_2=countries_by_points[2],
            p_1=countries_by_points[1],
        )

    async def get_vote_by_country_name(self, country_name: str) -> Vote | None:
        country_selections = Table("country_selections")
        q = Query.from_(country_selections).select(
            "user_id"
        ).where(country_selections.country_name == country_name)
        result = await self.execute_get_query(q)
        if not result:
            return None

        return await self.get_vote(result[0][0])

    async def get_votes(self) -> list[Vote]:
        votes = Table("votes")
        target_countries = Table("country_selections").as_("target_countries")
        voter_countries = Table("country_selections").as_("voter_countries")
        heralds = Table("heralds")
        q = Query.from_(votes).join(target_countries).on(
            votes.target_user_id == target_countries.user_id
        ).join(voter_countries).on(
            votes.voter_user_id == voter_countries.user_id
        ).join(heralds).on(
            votes.voter_user_id == heralds.user_id
        ).select(
            votes.voter_user_id,
            voter_countries.country_name,
            votes.points,
            target_countries.country_name,
        ).orderby(votes.voter_user_id, votes.points)
        result = await self.execute_get_query(q)
        if result is None:
            return []

        votes_by_user: dict[int, tuple[str, dict[int, str]]] = {}
        for voter_user_id, voter_country_name, points, country_name in result:
            if voter_user_id not in votes_by_user:
                votes_by_user[voter_user_id] = (voter_country_name, {})
            votes_by_user[voter_user_id][1][points] = country_name

        required_points = (12, 10, 8, 7, 6, 5, 4, 3, 2, 1)
        complete_votes = []
        for voter_user_id, (voter_country_name, countries_by_points) in votes_by_user.items():
            if set(countries_by_points) != set(required_points):
                continue

            complete_votes.append(
                Vote(
                    user_id=voter_user_id,
                    country_name=voter_country_name,
                    p_12=countries_by_points[12],
                    p_10=countries_by_points[10],
                    p_8=countries_by_points[8],
                    p_7=countries_by_points[7],
                    p_6=countries_by_points[6],
                    p_5=countries_by_points[5],
                    p_4=countries_by_points[4],
                    p_3=countries_by_points[3],
                    p_2=countries_by_points[2],
                    p_1=countries_by_points[1],
                )
            )

        return complete_votes
    
    async def save_application(self, application: Application) -> bool:
        if self.connection is None:
            return False

        async with self._write_lock:
            try:
                await self.connection.execute("BEGIN")
                if not await self._is_active_stage("applications_stage"):
                    await self.connection.rollback()
                    return False

                await self.connection.execute(
                    """
                    INSERT INTO applications (
                        user_id,
                        singer_name,
                        song_name,
                        video_link,
                        video_start,
                        video_end,
                        singer_photo
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        singer_name = excluded.singer_name,
                        song_name = excluded.song_name,
                        video_link = excluded.video_link,
                        video_start = excluded.video_start,
                        video_end = excluded.video_end,
                        singer_photo = excluded.singer_photo
                    """,
                    (
                        application.user_id,
                        application.singer_name,
                        application.song_name,
                        application.video_link,
                        application.video_start,
                        application.video_end,
                        application.singer_photo,
                    ),
                )
                await self.connection.commit()
            except aiosqlite.Error:
                await self.connection.rollback()
                return False

        return True
