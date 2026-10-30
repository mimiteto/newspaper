# Weather — Novi Iskar, 30 Oct 2026

Generated 30 Oct 2026 at 17:25 Europe/Sofia (EET, UTC+2); Open-Meteo values are as of 17:15 local and the wttr.in cross-check as of 17:28 local for Novi Iskar (42.7382 / 23.5975, 670 m elevation).

**Temperature.** A mild, saturated Friday: high 9.0 °C / low 7.8 °C for today, with 8.3 °C at the 17:15 reference hour (feels like 7.1 °C) and 0.20 mm in the 15-minute model interval ending there.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,cloud_cover&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code,sunrise,sunset&timezone=Europe%2FSofia&forecast_days=3
**Conditions.** Light rain (WMO code 61) at the reference hour under 100 % cloud cover, 96 % relative humidity and a 4 km/h wind; wttr.in reads the same air as light drizzle, 9 °C / feels 8 °C, 97 % humidity, and credits today with 0.0 hours of sunshine.
https://wttr.in/Novi+Iskar?format=j1
**Precipitation.** 7.20 mm booked for today at a 75 % peak probability; the direction for tomorrow is drier — 1.60 mm at 45 % with the high easing up to 10.6 °C — before a heavier 10.50 mm at 85 % on Sunday 1 November.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=precipitation_sum,precipitation_probability_max,temperature_2m_max&timezone=Europe%2FSofia&forecast_days=3
**Air & daylight.** US AQI 70 (moderate) at 17:00 with PM2.5 18.1 µg/m³, PM10 24.7 µg/m³, ozone 38.0 µg/m³ and NO₂ 14.0 µg/m³; the sun rose 06:56 and set 17:21, about 10 h 25 m of daylight, and tomorrow's sunset comes at 17:19.
https://air-quality-api.open-meteo.com/v1/air-quality?latitude=42.7382&longitude=23.5975&current=pm2_5,pm10,ozone,nitrogen_dioxide,us_aqi&timezone=Europe%2FSofia

Flags: the two providers disagree on tomorrow's high (Open-Meteo 10.6 °C vs wttr.in 10 °C) and on sunset (17:21 vs 17:23); wttr.in's j1 feed publishes no daily precipitation total, so the 7.20 / 1.60 / 10.50 mm figures are Open-Meteo model sums from a single model run. Caveat: `precipitation_probability_max` is the highest hourly probability in the day, not the probability of measurable rain over 24 h, and the Sunday 1 November total (10.50 mm) is the least stable of the three days.
