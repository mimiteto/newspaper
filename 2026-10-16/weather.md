# Weather — Novi Iskar, 16 Oct 2026

Generated 15:28 Europe/Sofia (EEST, UTC+3); Open-Meteo current sync 15:15 local, wttr.in cross-check 15:25.

**Temperature today.** High 10.0 °C / low 3.2 °C — cool afternoon, near-freezing tonight (Open-Meteo; wttr.in agrees at 10 °C now).
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=temperature_2m_max,temperature_2m_min&timezone=Europe%2FSofia

**Conditions.** Overcast with shower risk — 10.0 °C at 15:15 (feels 7.5 °C), 64% RH, wind 6–9 km/h; wttr.in reports light rain (0.5 mm) around its Kurilo-adjacent grid point.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&current=temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m&timezone=Europe%2FSofia
https://wttr.in/Novi+Iskar

**Precipitation.** ~1.6 mm expected today (78% chance, WMO 80 showers); tomorrow dry (0 mm, 8%) with a cold 2.2 °C night; Sunday turns mild at 13.8 °C with only trace rain risk.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=precipitation_sum,precipitation_probability_max&timezone=Europe%2FSofia

**Air/daylight.** PM2.5 4.4 µg/m³ (US AQI 60, "moderate" — first above-"good" reading this run); 11 h 02 m of daylight, sunrise 07:39, sunset 18:41.
https://air-quality-api.open-meteo.com/v1/air-quality?latitude=42.7382&longitude=23.5975&current=pm2_5,us_aqi&timezone=Europe%2FSofia

Flags: providers disagree on today's rain (Open-Meteo 1.6 mm showers vs wttr.in ~0.5 mm) and Open-Meteo's Sunday pair is internally odd (WMO 61 drizzle code with 5% probability) — treat Sunday's rain as negligible; tonight's 2–3 °C lows approach first-frost territory on open ground.
