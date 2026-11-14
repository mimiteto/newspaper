# Weather — Novi Iskar, Sat 14 Nov 2026

Generated for Europe/Sofia (UTC+2) from open-meteo (lat 42.7382, lon 23.5975) with a wttr.in cross-check; forecast read as of 14:00 local (12:00 UTC), 14 Nov 2026.

**Temperature today.** A cold front knocked the day down hard: high 14.1 °C / low 2.3 °C against 20.8 °C on 13 Nov (−6.7 °C day-over-day), with 6.5 °C at 14:00 and a 2.8 °C wind chill.

https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=temperature_2m_max,temperature_2m_min,weather_code&past_days=1&forecast_days=3&timezone=Europe/Sofia
https://wttr.in/Novi+Iskar

**Conditions.** Overcast with light drizzle at 14:00 — 6.5 °C, 73 % humidity, 90–100 % cloud cover, WNW wind ~13 km/h, WMO code 80 (rain showers) for the day.

https://wttr.in/Novi+Iskar?format=j1
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&current=temperature_2m,apparent_temperature,relative_humidity_2m,cloud_cover,wind_speed_10m,weather_code&timezone=Europe/Sofia

**Precipitation.** Only 0.5 mm expected today at a 35 % peak probability, then dry tomorrow (15 Nov: 0.0 mm, 13 % probability) before rain returns Sunday 16 Nov with 1.8 mm at 68 % probability.

https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=precipitation_sum,precipitation_probability_max&forecast_days=3&timezone=Europe/Sofia
https://wttr.in/Novi+Iskar?format=j1

**Air & daylight.** Air quality is good at 14:00 — European AQI 22 with PM2.5 6.0 µg/m³ and NO₂ 6.1 µg/m³ — but drifts to AQI 33 (PM2.5 11.4 µg/m³) by 18:00; daylight runs 9 h 48 m, sunrise 07:15, sunset 17:03, UV index peaking at 1.45.

https://air-quality-api.open-meteo.com/v1/air-quality?latitude=42.7382&longitude=23.5975&current=european_aqi,pm2_5,pm10,nitrogen_dioxide&hourly=european_aqi,pm2_5&timezone=Europe/Sofia
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=sunrise,sunset,uv_index_max&forecast_days=2&timezone=Europe/Sofia

Flags:
- Provider disagreement on today's high: open-meteo 14.1 °C vs wttr.in 11 °C (3.1 °C apart), and on today's rain — open-meteo 0.5 mm total vs wttr.in putting 1.1 mm in the 15:00 hour alone with a 72 % chance. The two agree on the direction (dry Saturday 15 Nov, wetter Sunday) but not the amounts.
- wttr.in's current observation is stamped 12:04 UTC while the open-meteo "current" block is 14:00 local, so the two "now" readings are ~2 h apart; treat the drizzle/humidity readings as an approximation, and note that the AQI forecast is a model estimate, not a station measurement.
