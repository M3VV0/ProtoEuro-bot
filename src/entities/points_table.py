from entities.application import Application
from entities.vote import Vote, get_points


class PointsTable:
    points: dict[str, int]
    country_flags: dict[str, str]
    included_countries: set[str]
    
    def __init__(self, applications: list[Application]):
        self.points = {
            application.country_name: 0
            for application in applications
        }
        self.country_flags = {
            application.country_name: application.country_flag
            for application in applications
        }
        self.included_countries = set()
    
    def update_table(self, vote: Vote) -> list[str]:
        sender = vote.country_name
        if sender in self.included_countries:
            return ["Баллы этой страны уже были учтены."]
        self.included_countries.add(sender)
        
        points_in_vote = get_points(vote)
        for country, points in points_in_vote.items():
            self.points[country] += points

        sorted_points = sorted(
            self.points.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        result = []
        for position, (country, total_points) in enumerate(sorted_points, start=1):
            country_name = country
            if position == 1:
                country_name = f"<b><u>{country}</u></b>"
            elif position <= 3:
                country_name = f"<b>{country}</b>"

            line = f"{self.country_flags[country]} {country_name} — {total_points}"
            points_received = points_in_vote.get(country)
            if points_received is not None:
                line += f" <i>(+{points_received})</i>"
            result.append(line)

        return result

    def show_table(self) -> list[str]:
        sorted_points = sorted(
            self.points.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        return [
            f"{self.country_flags[country]} {country} — {total_points}"
            for country, total_points in sorted_points
        ]
