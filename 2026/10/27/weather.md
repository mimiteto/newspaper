# Weather — Novi Iskar, 27 Oct 2026

Generated for Europe/Sofia (UTC+2), forecast read as of 10:15 local from open-meteo and cross-checked against wttr.in at 10:20 local.

**Temperature today.** Cool autumn day with a high of 10.2 °C and a low of 1.9 °C; 5.6 °C on the board at 10:15 local, feeling like 2.6 °C.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=weather_code,temperature_2m_max,temperature_2m_min&forecast_days=3&timezone=Europe%2FSofia
https://wttr.in/Novi+Iskar?format=%l|%c|%t|%f

**Conditions.** Partly cloudy to overcast — 70 % cloud cover, wind 8.4 km/h from the west, relative humidity 79 % at the reference hour.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,cloud_cover,wind_speed_10m,wind_direction_10m&timezone=Europe%2FSofia
https://wttr.in/Novi+Iskar

**Precipitation.** Dry today: 0.0 mm with a 5 % peak probability; tomorrow stays at 0.0 mm but the probability doubles to 15 % under fog/low cloud (WMO code 45) and rises again to 18 % on 29 Oct — the direction of travel is wetter, but not a rainy day in the window.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=precipitation_sum,precipitation_probability_max,weather_code&forecast_days=3&timezone=Europe%2FSofia

**Air & daylight.** European AQI 29 (US AQI 58) with PM2.5 at 9.7 µg/m³ and ozone 48.0 µg/m³ at 10:00 local; sunrise 06:53 and sunset 17:25 give about 10 h 32 min of daylight against a maximum UV index of 2.75.
https://air-quality-api.open-meteo.com/v1/air-quality?latitude=42.7382&longitude=23.5975&current=european_aqi,us_aqi,pm2_5,pm10,ozone&timezone=Europe%2FSofia

Flags:
- Peak-temperature disagreement between providers: open-meteo has today's high at 10.2 °C, wttr.in at 8 °C; the current reads also differ (5.6 °C / feels 2.6 °C at 10:15 vs 6 °C / feels 4 °C at 10:20).
- Rain-signal disagreement: open-meteo holds today at 0.0 mm and a 5 % maximum probability while wttr.in shows 16–20 % "patchy rain nearby" around midday and 23–30 % tomorrow — treat the open-meteo dry case as the optimistic branch, and note wttr.in credits only 3.0 sun hours for today against open-meteo's partly-cloudy codes.
- Caveat: the air-quality block is a model field for the 42.7 / 23.6 grid cell rather than a street-level station, and the 1.9 °C minimum is a screen-height value — frost at ground level in the valley is possible even with the official minimum above zero.
