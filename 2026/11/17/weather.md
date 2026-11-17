# Weather — Novi Iskar, 17 Nov 2026

Forecast for Novi Iskar (lat 42.7382, lon 23.5975), Europe/Sofia (EET, UTC+2), read at 10:15 local on 17 Nov 2026.

**Temperature today.** High 13.9 °C, low 6.2 °C — 10.4 °C at the 10:15 observation (feels like 9.0 °C), after a 4.1 °C-cold, wet Monday.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=temperature_2m_max,temperature_2m_min&current=temperature_2m,apparent_temperature&timezone=Europe%2FSofia
https://wttr.in/Novi+Iskar (10 °C, feels 9 °C; day range 6–15 °C)

**Conditions.** Overcast with occasional bright spells (WMO code 3, 63 % cloud cover), dry at the observation hour, light 5.4 km/h west wind, 1012.4 hPa.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&current=weather_code,cloud_cover,wind_speed_10m,pressure_msl&timezone=Europe%2FSofia
https://wttr.in/Novi+Iskar?format=j1 ("Partly Cloudy", 50 % cloud, 6 km/h W)

**Precipitation.** Only 0.5 mm left for today and all of it fell before ~05:00 (peak probability 85 %, then 0 % for the rest of the day); tomorrow goes the wetter way — 2.3 mm of light rain (WMO 61) centred 07:00–10:00, then a mild 16.0 °C afternoon.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&hourly=precipitation,precipitation_probability,weather_code&daily=precipitation_sum,precipitation_probability_max&forecast_days=2&timezone=Europe%2FSofia
https://wttr.in/Novi+Iskar?format=j1 (1.0 mm today / 1.3 mm tomorrow, max rain chance 61 % / 55 %)

**Air & daylight.** Air is clean — US AQI 39, European AQI 22, PM2.5 5.8 µg/m³, PM10 7.7 µg/m³, ozone 44.0 µg/m³ at 10:00; sunrise 07:19, sunset 17:01 (9 h 41 min of daylight), UV index max 2.4.
https://air-quality-api.open-meteo.com/v1/air-quality?latitude=42.7382&longitude=23.5975&current=pm2_5,pm10,ozone,us_aqi,european_aqi&timezone=Europe%2FSofia

Flags: the two providers disagree on today's rain — open-meteo 0.5 mm at 85 % peak probability (all pre-dawn) vs wttr.in 1.0 mm at 61 % — and on tomorrow (2.3 mm vs 1.3 mm); daily high is 13.9 °C vs 15 °C, sunrise differs by 2 min (07:19 vs 07:21). Caveat: model forecast read at 10:15 local, about 5 h before the daily maximum, so today's high and tomorrow's rain totals are the least stable figures here.
