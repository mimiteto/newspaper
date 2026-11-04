# Weather — Novi Iskar, 4 Nov 2026

Forecast as of 12:05 local (Europe/Sofia, GMT+2); Open-Meteo model data for lat 42.7382 / lon 23.5975 (station elevation 670 m), cross-checked against wttr.in (nearest station resolves to Kurilo, 42.817 / 23.350, observation 10:05 UTC).

**Temperature today.** Mostly cloudy and cool, high 8.3 °C / low 5.8 °C, with 7.1 °C at 12:00 (feels like 5.1 °C) and the day's warmest hour at 15:00; wttr.in has the same shape but slightly cooler numbers (max 8 °C / min 5 °C).
- https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=temperature_2m_max,temperature_2m_min,weather_code&timezone=Europe/Sofia
- https://wttr.in/Novi+Iskar?format=j1

**Conditions.** Overcast all day — WMO code 3 (100 % cloud cover) at 12:00, wind NNW 4–5 km/h, sea-level pressure 1023.2 hPa (Open-Meteo) vs 1025 hPa (wttr.in), visibility 10 km, "patchy rain nearby" per wttr.in.
- https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&current=temperature_2m,cloud_cover,pressure_msl,wind_speed_10m,weather_code&timezone=Europe/Sofia
- https://wttr.in/Novi+Iskar?format=j1

**Precipitation.** Almost nothing today — 0.1 mm total (only the 00:00 hour is wet, 30 % probability at its peak) — but the trend turns wetter overnight: 0.7 mm forecast for tomorrow (Thu 5 Nov, 33 % probability) with the heaviest hours between 02:00–06:00, then easing to 0.1 mm and 0 % probability on Fri 6 Nov.
- https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=precipitation_sum,precipitation_probability_max&timezone=Europe/Sofia

**Air & daylight.** Air quality is good — European AQI 17 with PM10 4.4 µg/m³ and PM2.5 4.3 µg/m³ — and the UV index stays low (0.65 now, daily max 0.35) while daylight is short: sunrise 07:03, sunset 17:14, i.e. about 10 h 11 min of light.
- https://air-quality-api.open-meteo.com/v1/air-quality?latitude=42.7382&longitude=23.5975&current=european_aqi,pm10,pm2_5,uv_index&timezone=Europe/Sofia
- https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=sunrise,sunset,uv_index_max&timezone=Europe/Sofia

Flags: the two providers disagree in both direction and amount — Open-Meteo keeps hourly precipitation at 0.0 mm from 01:00 to 13:00 (with an 0.1 mm tick only at 00:00) yet still books 0.7 mm of rain for tomorrow and labels today WMO 61 "slight rain", while wttr.in keeps a 31–35 % rain chance running all through today and tomorrow with only ~0.1 mm per 3-hour block; wttr.in also has tomorrow's low 6 °C versus Open-Meteo's 2.3 °C (a 3.7 °C spread that matters for frost risk in the Iskar valley). Caveat: wttr.in's grid point sits around 12 km south-west of Novi Iskar at a different elevation, so treat its numbers as a neighbouring-town check rather than a like-for-like reading, and re-pull before relying on the Thursday rain.