
def getMedalUrl(place, total):
    if place == 1:
        return "https://static-api.nkstatic.com/appdocs/4/assets/opendata/a7e4a355bbc2614d4ac92282fdc6d511_season_medal_hom_1st.png"
    if place == 2:
        return "https://static-api.nkstatic.com/appdocs/4/assets/opendata/cf542a65660000c64706c01a38d4994d_season_medal_hom_2nd.png"
    if place == 3:
        return "https://static-api.nkstatic.com/appdocs/4/assets/opendata/f380217fbca43fd42385fa39796c4941_season_medal_hom_3rd.png"
    if place <= 10:
        return "https://static-api.nkstatic.com/appdocs/4/assets/opendata/d846dc3f51fefe7e68257e03fe395734_season_medal_hom_top10.png"
    if place <= 25:
        return "https://static-api.nkstatic.com/appdocs/4/assets/opendata/224beda91928a669422485b44e19e7a3_season_medal_hom_top25place.png"
    if place <= 50:
        return "https://static-api.nkstatic.com/appdocs/4/assets/opendata/1a93a5d608121e09dcbc92454d9f9647_season_medal_hom_top50place.png"
    if place <= 100:
        return "https://static-api.nkstatic.com/appdocs/4/assets/opendata/65e7f5fab83fa6ab1480c65ed35f6df3_season_medal_hom_top100.png"
    percent = (place*100)//total
    if percent <= 10:
        return "https://static-api.nkstatic.com/appdocs/4/assets/opendata/c313210cdf25dc67c7de4167b46bae0a_season_medal_hom_top10perc.png"
    if percent <= 25:
        return "https://static-api.nkstatic.com/appdocs/4/assets/opendata/dbcf728f0855687c361a655d71c3bd8b_season_medal_hom_top25.png"
    if percent <= 50:
        return "https://static-api.nkstatic.com/appdocs/4/assets/opendata/0b96d75c9f050b98f7328c73400e63bf_season_medal_hom_top50.png"
    if percent <= 75:
        return "https://static-api.nkstatic.com/appdocs/4/assets/opendata/c37ece72609d1dc09def01a4819e5ac9_season_medal_hom_top75.png"
    return "https://static-api.nkstatic.com/appdocs/4/assets/opendata/bd26ab9abf49c99cc82b4991d4db7836_season_medal_hom.png"
