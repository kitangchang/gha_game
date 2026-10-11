Drop an earthquake catalogue CSV in this folder to play real days:

  * archive.csv from the eq_stats app (event_id, origin_time, latitude, longitude,
    depth, magnitude, description, creation_time, ...), or
  * a GeoNet quakesearch CSV export, or
  * FDSN event text output (#EventID|Time|Latitude|Longitude|Depth/km|...).

The newest .csv/.txt file here is used. Without one, the game generates a synthetic
NZ catalogue. Run  python tools/check_catalog.py  to see what the game picked up.
