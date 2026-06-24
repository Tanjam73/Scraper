# Mumbai Monsoon Rail Data Collector

Captures, with **zero daily effort**, the raw data you need to later predict which
sections of the Western / Central / Harbour lines fail during heavy rain.

It writes two logs:

- `data/rainfall.csv` — one row per location, every 30 min. A rainfall time series.
- `data/disruptions.csv` — one row per *new* disruption news item (deduped).

The whole point of the project is the **join** between these two — *"this ward
crossed this much rain, and that section failed this many minutes later"* — but
that's the analysis you do later, on a study break. Right now you only need the
data to exist. The monsoon is the one thing you can't get back.

## Sources (both free, no API keys, no signup)

- **Rainfall:** [Open-Meteo](https://open-meteo.com) — current precipitation per lat/long.
- **Disruptions:** Google News RSS — headlines matching waterlogging / suspended / delay etc.

## One-time setup (~15 minutes, then never touch it)

1. Make a **public** GitHub repo (public = unlimited Actions minutes; private caps at 2000/mo and this would blow past it).
2. Drop in `scrape.py`, `requirements.txt`, and the `.github/workflows/collect.yml` file.
3. Push. Go to the repo's **Settings → Actions → General → Workflow permissions** and set **Read and write permissions** (lets the bot commit data back).
4. Open the **Actions** tab → select **collect** → **Run workflow** once to confirm it works. You should see `data/rainfall.csv` and `data/disruptions.csv` appear with rows.
5. Done. It now runs every 30 minutes on its own and commits the data. Forget about it until intern season ends.

## When you surface (after the monsoon)

- `git pull` → you have months of rainfall + a timestamped disruption log.
- Join them, look for the rainfall→failure lag per section, and *that's* your dataset — the thing that doesn't exist anywhere else.

## Honest limitations (so nothing surprises you later)

- **Rainfall resolution:** Open-Meteo's grid is ~11 km, so nearby stations may show identical values. Good enough to find the rain↔failure signal. For true *ward-level* rain, swap in BMC's automatic-weather-station data later — the CSV columns stay the same, so nothing downstream breaks.
- **Disruptions via news, not the railway's own feed:** news RSS lags the railway's X posts by a few minutes and misses small delays. It reliably catches the *real* events (suspensions, major waterlogging), which are the ones you care about. If you ever get an X API key, add it as a third source — the script is built to tolerate adding/removing sources.
- **Tune the keywords:** edit `NEWS_QUERIES` and `DISRUPTION_WORDS` in `scrape.py` if you see junk getting through or real events slipping past.

## Run it locally (optional sanity check)

```bash
pip install -r requirements.txt
python scrape.py
cat data/rainfall.csv
```
