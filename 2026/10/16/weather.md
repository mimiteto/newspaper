# Weather — Novi Iskar, 16 Oct 2026

Generated 16:58 Europe/Sofia (EEST, UTC+3); forecast anchored on the Open-Meteo 16:45 local sync, cross-checked against wttr.in at 16:42.

**Temperature today.** High 10.0 °C / low 3.2 °C — a cool, sunless afternoon, and tomorrow night's low dips to 2.2 °C (Open-Meteo daily max/min; wttr.in reads the same 10 °C right now).
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=temperature_2m_max,temperature_2m_min&timezone=Europe%2FSofia

**Conditions.** WMO code 3 (overcast) at 9.4 °C, feels-like 6.5 °C, 64% RH, 100% cloud cover, wind 8.4 km/h; the daily code is 80 (rain showers) and wttr.in still reports 🌦 at +10 °C, feels +9 °C, wind ↙ 9 km/h.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&current=temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,cloud_cover&timezone=Europe%2FSofia
https://wttr.in/Novi+Iskar

**Precipitation.** 1.60 mm today at 78% peak probability; tomorrow stays dry (0.00 mm, 8%, 10.4 °C high) before Sunday turns milder at 13.8 °C with a nominal 0.50 mm.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=precipitation_sum,precipitation_probability_max,weather_code&timezone=Europe%2FSofia

**Air/daylight.** PM2.5 4.8 µg/m³ and PM10 5.4 µg/m³ (US AQI 59 "moderate", European AQI 24) as of 16:00 local; 11 h 02 m of daylight, sunrise 07:39, sunset 18:41 — tomorrow sets a minute earlier, at 18:40.
https://air-quality-api.open-meteo.com/v1/air-quality?latitude=42.7382&longitude=23.5975&current=pm2_5,pm10,us_aqi,european_aqi&timezone=Europe%2FSofia
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=sunrise,sunset&timezone=Europe%2FSofia&forecast_days=2

Flags: the providers split on today's rain — Open-Meteo 1.60 mm at 78% versus wttr.in 0.5 mm — and wttr.in's 58% RH against Open-Meteo's 64% points to a different grid point, so treat any shower over Novi Iskar itself as local and brief; Open-Meteo's Sunday pair is internally inconsistent (WMO 61 rain code at 5% probability), so read Sunday as dry; tonight's 3.2 °C and Saturday's 2.2 °C approach first-frost territory on open ground toward the Iskar dam.
