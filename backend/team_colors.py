"""Team colors for the app theme and the exported packets (colors only, no logos).

primary   = main brand color (headers, buttons)
secondary = second brand color (accents)
on_primary = text color that reads well on primary
"""

MLB = {"primary": "#041E42", "secondary": "#BF0D3E", "on_primary": "#FFFFFF"}  # league navy and red

TEAM_COLORS: dict[int, dict[str, str]] = {
    108: {"primary": "#BA0021", "secondary": "#003263"},  # Angels
    109: {"primary": "#A71930", "secondary": "#E3D4AD"},  # D-backs
    110: {"primary": "#DF4601", "secondary": "#000000"},  # Orioles
    111: {"primary": "#BD3039", "secondary": "#0C2340"},  # Red Sox
    112: {"primary": "#0E3386", "secondary": "#CC3433"},  # Cubs
    113: {"primary": "#C6011F", "secondary": "#000000"},  # Reds
    114: {"primary": "#00385D", "secondary": "#E50022"},  # Guardians
    115: {"primary": "#333366", "secondary": "#C4CED4"},  # Rockies
    116: {"primary": "#0C2340", "secondary": "#FA4616"},  # Tigers
    117: {"primary": "#002D62", "secondary": "#EB6E1F"},  # Astros
    118: {"primary": "#004687", "secondary": "#BD9B60"},  # Royals
    119: {"primary": "#005A9C", "secondary": "#EF3E42"},  # Dodgers
    120: {"primary": "#AB0003", "secondary": "#14225A"},  # Nationals
    121: {"primary": "#002D72", "secondary": "#FF5910"},  # Mets
    133: {"primary": "#003831", "secondary": "#EFB21E"},  # Athletics
    134: {"primary": "#27251F", "secondary": "#FDB827"},  # Pirates
    135: {"primary": "#2F241D", "secondary": "#FFC425"},  # Padres
    136: {"primary": "#0C2C56", "secondary": "#005C5C"},  # Mariners
    137: {"primary": "#27251F", "secondary": "#FD5A1E"},  # Giants
    138: {"primary": "#C41E3A", "secondary": "#0C2340"},  # Cardinals
    139: {"primary": "#092C5C", "secondary": "#8FBCE6"},  # Rays
    140: {"primary": "#003278", "secondary": "#C0111F"},  # Rangers
    141: {"primary": "#134A8E", "secondary": "#E8291C"},  # Blue Jays
    142: {"primary": "#002B5C", "secondary": "#D31145"},  # Twins
    143: {"primary": "#E81828", "secondary": "#002D72"},  # Phillies
    144: {"primary": "#13274F", "secondary": "#CE1141"},  # Braves
    145: {"primary": "#27251F", "secondary": "#C4CED4"},  # White Sox
    146: {"primary": "#00A3E0", "secondary": "#EF3340"},  # Marlins
    147: {"primary": "#0C2340", "secondary": "#C4CED3"},  # Yankees
    158: {"primary": "#12284B", "secondary": "#FFC52F"},  # Brewers
}


def colors(team_id: int | None) -> dict[str, str]:
    c = TEAM_COLORS.get(team_id or 0)
    return {**c, "on_primary": "#FFFFFF"} if c else dict(MLB)
