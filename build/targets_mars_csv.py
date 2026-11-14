"""
THE MARS TARGETS -- NASA's own candidate human sites, not a list we invented.

    python build/targets_mars_csv.py

Writes  sources/mars_site_candidates_v1.csv   every sourced candidate (write-once)
        sources/targets_mars_v1.csv           the six presets (write-once)

SOURCE
    NASA's "First Landing Site / Exploration Zone Workshop for Human Missions
    to the Surface of Mars", Lunar and Planetary Institute, Houston, 27-30
    October 2015. Teams proposed Exploration Zones (EZ). Abstracts:
    https://www.hou.usra.edu/meetings/explorationzone2015/pdf/<number>.pdf

    NASA's definition of an EZ (First Announcement, read):
    "a collection of Regions of Interest that are located within
    approximately 100 kilometers of a centralized landing site."
    Limits: latitude within +/- 50 degrees, elevation no higher than +2 km.

    Later work: Golombek et al. (2021) LPSC abstract 2420, the SpaceX / JPL
    candidate Starship landing sites, Table 1.

GEOMETRY -- nothing invented
    Each preset is a disc of NASA's own EZ radius, 100 km, centred where the
    proposing team wrote its centre. About 680 cells at Nside 512. That is
    larger than any Artemis III region (the largest is 4,452 km2 against
    31,416 km2), so a Mars target is a ZONE: crater floor, rim and plains
    together. The null draws patches of the same size, so the test stays fair.

HOW THE SIX WERE CHOSEN -- by source, stated before any distance exists
    A. Every 2015 Exploration Zone inside which a rover has since driven:
       Jezero (Perseverance), Gale (Curiosity), Meridiani (Opportunity),
       Gusev (Spirit). Four zones with ground truth.
    B. One zone in each of the two mid-latitude ICE provinces that drew
       several independent proposals in 2015:
       Arcadia - Erebus - Phlegra  -> Erebus Montes (Viola), because the
           2021 SpaceX / JPL prime site EM-16 lies inside it;
       Deuteronilus - Protonilus   -> Deuteronilus Mensae (Head), the
           proposal that states an explicit centre.
    Data coverage was NOT a criterion. It is reported by build/targets.py.

LATITUDE TYPE
    No abstract says planetocentric or planetographic. The two differ by at
    most 0.33 degrees (about 20 km) at 39 N and by less near the equator.
    That is small against a 100 km radius; it is recorded, not corrected.

VERIFICATION
    "twice": the coordinate was read in the abstract text by the research
    pass and again by a search of the saved text extract on 10 Nov 2026.
    "once": read by the research pass only.
"""

import csv
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

SRC = os.path.join(C.ROOT, "sources")
ALL = os.path.join(SRC, "mars_site_candidates_v1.csv")
SIX = os.path.join(SRC, "targets_mars_v1.csv")
EZ_URL = "https://www.hou.usra.edu/meetings/explorationzone2015/pdf/%s.pdf"
GOL = "https://www.hou.usra.edu/meetings/lpsc2021/pdf/2420.pdf"
EZ_RADIUS_KM = 100.0

# list, name, first author, abstract, lat N, lon E (0-360), as written, verified
EZ = [
    ("Jezero crater watershed", "Mustard", "1034", 17.747, 77.037, "17.747 N 77.037 E, 'the center of the Exploration Zone'", "twice"),
    ("Gale crater", "Calef", "1020", -4.5965, 137.4019, "137.4019 longitude, -4.5965 latitude, centre of the final MSL landing ellipse", "twice"),
    ("Gale crater (Yun)", "Yun", "1022", -4.6, 137.0, "4.6 S 137 E", "once"),
    ("Mawrth Vallis", "Horgan", "1009", 24.3, 340.8, "near 340.8 E, 24.3 N", "once"),
    ("Southern Meridiani, Endeavour", "Clarke", "1057", -3.174, 355.483, "Longitude 4d31'2.33\"W, Latitude 3d10'26.25\"S", "twice"),
    ("SW Sinus Meridiani", "Wilkinson", "1042", -2.2526, 353.5665, "6.4335 W, 2.2526 S", "once"),
    ("Eastern Melas Chasma", "McEwen", "1007", -11.7, 290.0, "center ~11.7 S, 290.0 E", "once"),
    ("Coprates Chasma, west", "Mojarro", "1036", -11.684, 293.367, "293.367 E, -11.684 N", "once"),
    ("Gusev crater", "Longo", "1008", -14.5, 175.4, "14.5 S, 175.4 E (the crater; no separate EZ centre given)", "twice"),
    ("Gusev - Apollinaris Sulci", "Rice", "1046", -13.0, 175.0, "near 13 S; 175 E", "once"),
    ("Apollinaris Sulci", "Kerber", "1043", -12.667, 176.667, "12d40'S, 176d40'E", "once"),
    ("Deuteronilus Mensae", "Head", "1033", 39.11, 23.199, "(39.11 N, 23.199 E)", "twice"),
    ("Protonilus Mensae", "Gallegos", "1053", 42.187, 48.062, "48.062E, 42.187N", "once"),
    ("Erebus Montes", "Viola", "1011", 39.0, 192.1, "centered near 192.1 E, 39.0 N", "twice"),
    ("Acheron Fossae", "Viola", "1011", 39.8, 220.6, "near 220.6 E, 39.8 N", "once"),
    ("Phlegra Dorsa, Arcadia", "Barker", "1002", 39.0, 172.0, "39 N 172 E", "once"),
    ("Mid-latitude ice, Amazonis", "Stoker", "1018", 46.16, 188.8, "landing site 46.16N, 188.8E", "once"),
    ("Nili Fossae", "Markle", "1010", 22.05, 76.95, "approximately at 22.05 N, 76.95 E", "once"),
    ("Hellas rim", "Levy", "1037", -39.05, 101.91, "39.05 S, 101.91 E", "once"),
    ("Eastern Hellas rim", "Rice", "1038", -40.0, 104.0, "near 40 S; 104 E", "once"),
    ("Mesopotamia, east Hellas", "Gallegos", "1035", -35.352, 94.02, "94.02E, 35.352S", "once"),
    ("Chryse, Viking 1", "Farrell", "1019", 22.3, 311.7, "22.3 N, 48.3 W", "once"),
    ("Valles Marineris mouth, south Acidalia", "Kochemasov", "1006", 20.0, 320.0, "40 W, 20 N", "once"),
    ("Eastern Valles Marineris outlet", "Clifford", "1054", -4.1, 324.8, "(-4.1, -35.2)", "once"),
    ("Noctis Landing", "Lee", "1050", -6.494, 267.547, "6d29'38.33\"S, 92d27'12.34\"W", "once"),
    ("Hebrus Valles", "Davila", "1012", 20.083, 126.633, "20d05'N, 126d38'E", "once"),
    ("McLaughlin crater", "Michalski", "1025", 21.9, 337.6, "337.6E, 21.9N", "once"),
    ("Aram Chaos", "Sibille", "1048", 2.417, 339.967, "2d25'N, 20d02'W", "once"),
    ("Firsoff crater, south", "Ori", "1026", 0.391, 351.638, "0d23'28\"N, 8d21'45\"W", "once"),
    ("Ismenius Cavus", "Mangold", "1027", 33.817, 17.167, "33d49'N, 17d10'E", "once"),
    ("Huygens crater", "Ackiss", "1032", -13.5, 55.5, "13.5 S, 55.5 E", "once"),
    ("Hadriacus Palus", "Skinner", "1052", -26.84, 77.47, "77.47E, -26.84N", "once"),
    ("Ausonia Cavus", "Hamilton", "1045", -32.0, 96.5, "32.0S, 96.5E", "once"),
    ("Kasei Valles", "Hamilton", "1045", 24.81, 287.37, "24.81N, 287.37E", "once"),
    ("Hale crater", "Stillman", "1028", -35.30, 323.14, "landing site 35.30S, 323.14E", "once"),
    ("West Noachis Terra", "Hill", "1021", -37.4214, 350.5785, "350.5785 E, -37.4214 N", "once"),
    ("Equatorial Valles Marineris", "Mitchell", "1023", -18.83, 310.79, "-18.83 N, 310.79 E", "once"),
    ("South Nectaris Fossae", "Boatwright", "1005", -28.88, 300.29, "28.88 S 300.29 E", "once"),
    ("Columbus crater", "Lynch", "1041", -29.0, 194.0, "29 S, 166 W", "once"),
    ("Newton crater", "Laine", "1015", -40.6, 200.0, "40.6 S / 200 E", "once"),
    ("Copernicus crater", "Westenberg", "1029", -49.2, 190.8, "49.2 S, 169.2 W", "once"),
    ("Cerberus", "Wright", "1017", 10.0, 162.0, "10 N, 162 E", "once"),
    ("Zephyria Planum hills", "Yakovlev", "1016", -1.372, 157.142, "1d22.3'S; 157d8.5'E", "once"),
]
GOLOMBEK = [
    ("PM-1 Phlegra Montes", 35.23, 163.95, "prime"),
    ("AP-1 Arcadia Planitia", 39.8, 202.1, "prime"),
    ("AP-9 Arcadia Planitia", 40.02, 203.35, "prime"),
    ("EM-16 Erebus Montes", 39.89, 192.03, "prime"),
    ("AP-8 Arcadia Planitia", 40.75, 201.3, "secondary 1"),
    ("EM-15 Erebus Montes", 39.75, 195.62, "secondary 2"),
    ("PM-7 Phlegra Montes", 36.43, 162.16, "secondary 3"),
]
LANDED = [
    ("Perseverance", 18.44, 77.45, "Newman et al. 2022 Sci. Adv.", "https://pmc.ncbi.nlm.nih.gov/articles/PMC9132482/"),
    ("Curiosity", -4.5895, 137.4417, "Malin et al. 2017 citing Vasavada et al. 2014", "https://pmc.ncbi.nlm.nih.gov/articles/PMC5652233/"),
    ("Opportunity", -1.946, 354.473, "NSSDCA 2003-032A, IAU 2000 body-centred", "https://nssdc.gsfc.nasa.gov/nmc/spacecraft/display.action?id=2003-032A"),
    ("Spirit", -14.572, 175.478, "NSSDCA 2003-027A", "https://nssdc.gsfc.nasa.gov/nmc/spacecraft/display.action?id=2003-027A"),
    ("InSight", 4.502, 135.623, "Golombek et al. 2020 Nat. Commun.", "https://pmc.ncbi.nlm.nih.gov/articles/PMC7039939/"),
    ("Phoenix", 68.22, 234.25, "Smith et al. 2009 Science 325:58, areocentric", ""),
    ("Viking 1", 22.27, 312.05, "NSSDCA 1975-075C, planetocentric", "https://nssdc.gsfc.nasa.gov/nmc/spacecraft/display.action?id=1975-075C"),
    ("Zhurong", 25.07, 109.93, "NASA GISS Mars24 citing Liu et al. 2022", "https://www.giss.nasa.gov/tools/mars24/help/landers.html"),
    ("Oxia Planum (ExoMars, selected)", 18.20, 335.45, "2024 JGR Planets paper", "https://pmc.ncbi.nlm.nih.gov/articles/PMC11583114/"),
]
# preset name -> (EZ row name, why, rover or later site inside it)
PRESETS = [
    ("Jezero crater", "Jezero crater watershed", "A: a rover has driven inside this zone", "Perseverance, 18.44 N 77.45 E, 47 km from the zone centre"),
    ("Gale crater", "Gale crater", "A: a rover has driven inside this zone", "Curiosity, 4.5895 S 137.4417 E, 2 km from the zone centre"),
    ("Meridiani Planum, Endeavour", "Southern Meridiani, Endeavour", "A: a rover has driven inside this zone", "Opportunity landed at 1.946 S 354.473 E, 94 km from the zone centre, and drove to Endeavour crater"),
    ("Gusev crater", "Gusev crater", "A: a rover has driven inside this zone", "Spirit, 14.572 S 175.478 E, 6 km from the zone centre"),
    ("Erebus Montes, Arcadia", "Erebus Montes", "B: mid-latitude ice province Arcadia - Erebus - Phlegra", "SpaceX / JPL prime site EM-16, 39.89 N 192.03 E (Golombek et al. 2021), 53 km from the zone centre"),
    ("Deuteronilus Mensae", "Deuteronilus Mensae", "B: mid-latitude ice province Deuteronilus - Protonilus", "no landed mission; glacier ice mapped by radar is the resource"),
]


def write_once(path, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    text = buf.getvalue()
    if os.path.exists(path):
        if io.open(path, encoding="utf-8", newline="").read() == text:
            print("unchanged, already on disk:", path)
            return
        raise SystemExit(f"REFUSED: {path} exists and differs; sources/ is write-once")
    io.open(path + ".part", "w", encoding="utf-8", newline="").write(text)
    os.replace(path + ".part", path)
    print("wrote", path, f"({len(rows)} rows)")


def main():
    rows = []
    for name, author, num, lat, lon, written, ver in EZ:
        rows.append(["EZ 2015", name, lat, lon, author, num, EZ_URL % num,
                     "conference abstract (NASA EZ workshop 2015)", written, ver, ""])
    for name, lat, lon, status in GOLOMBEK:
        rows.append(["Starship candidate 2021", name, lat, lon, "Golombek", "2420", GOL,
                     "conference abstract (LPSC 2021), Table 1", f"{lat} N, {lon} E", "once", status])
    for name, lat, lon, src, url in LANDED:
        rows.append(["landed or selected mission", name, lat, lon, "", "", url, src,
                     f"{lat}, {lon}", "once", ""])
    write_once(ALL, ["list", "name", "lat_N", "lon_E_0_360", "first_author",
                     "abstract", "source_url", "source_kind", "as_written",
                     "verified", "status"], rows)

    by = {r[0]: r for r in EZ}
    six = []
    for preset, ezname, basis, inside in PRESETS:
        _, author, num, lat, lon, written, ver = by[ezname]
        if ver != "twice":
            raise SystemExit(f"{preset}: a preset must be verified twice")
        six.append([preset, lat, lon, "disc", EZ_RADIUS_KM, "", "",
                    f"2015 NASA Exploration Zone proposal, {author} et al., abstract {num}; centre as written: {written}",
                    EZ_URL % num,
                    "conference abstract (NASA EZ workshop 2015); radius is NASA's EZ definition",
                    f"{inside}. Latitude type not stated in the abstract (at most 0.33 deg, 20 km, at 39 N).",
                    "NASA Exploration Zone", basis, EZ_RADIUS_KM])
    write_once(SIX, ["name", "center_lat", "center_lon", "geometry", "radius_km",
                     "vertices_lonlat", "edges_straight_in", "geometry_source",
                     "source_url", "source_kind", "notes", "kind",
                     "selection_basis", "ez_radius_km"], six)
    return 0


if __name__ == "__main__":
    sys.exit(main())
