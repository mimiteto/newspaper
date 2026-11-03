# Weather — Novi Iskar, 3 Nov 2026

Generated 3 Nov 2026 at 21:14 Europe/Sofia (EET, UTC+2); Open-Meteo values are as of 21:00 local and the wttr.in cross-check as of 21:12 local for Novi Iskar (42.7382 / 23.5975, 670 m elevation).

**Temperature.** A cool, damp Saturday evening into a raw Sunday: high 10.7 °C / low 4.6 °C for today, with 8.3 °C at the 21:00 reference hour (feels like 6.9 °C) and 0.00 mm in the 15-minute model interval ending there.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,cloud_cover&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code,sunrise,sunset&timezone=Europe%2FSofia&forecast_days=3
**Conditions.** Overcast (WMO code 3) at the reference hour under 98 % cloud cover, 91 % relative humidity and a 11 km/h ESE wind; wttr.in reads the same air as cloudy, 9 °C / feels 7 °C, 93 % humidity, and credits today with 1.5 hours of sunshine.
https://wttr.in/Novi+Iskar?format=j1
**Precipitation.** 4.10 mm booked for today at a 65 % peak probability; the direction for tomorrow is wetter — 9.70 mm at 80 % with the high easing to 9.6 °C — before a drier 1.20 mm at 35 % on Monday 9 November.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=precipitation_sum,precipitation_probability_max,temperature_2m_max&timezone=Europe%2FSofia&forecast_days=3
**Air & daylight.** US AQI 62 (moderate) at 21:00 with PM2.5 14.9 µg/m³, PM10 21.3 µg/m³, ozone 41.0 µg/m³ and NO₂ 12.6 µg/m³; the sun rose 06:59 and set 17:16, about 10 h 17 m of daylight, and tomorrow's sunset comes at 17:14.
https://air-quality-api.open-meteo.com/v1/air-quality?latitude=42.7382&longitude=23.5975&current=pm2_5,pm10,ozone,nitrogen_dioxide,us_aqi&timezone=Europe%2FSofia

Flags: the two providers disagree on tomorrow's high (Open-Meteo 9.6 °C vs wttr.in 8 °C) and on tonight's minimum (4.6 °C vs 3 °C); wttr.in's j1 feed publishes no daily precipitation total, so the 4.10 / 9.70 mm figures are Open-Meteo model sums from a single model run. Caveat: `precipitation_probability_max` is the highest hourly probability in the day, not the probability of measurable rain over 24 h, and the Sunday 9 November total is the least stable of the three days.
