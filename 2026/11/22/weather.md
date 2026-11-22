# Weather — Novi Iskar, 22 Nov 2026

Generated 2026-11-22 09:19 Europe/Sofia (UTC+02:00); the forecast is as of 09:15 local (open-meteo current block) and the cross-check observation is stamped 07:19 UTC / 09:19 local (wttr.in).

**Temperature today.** High 12.0 °C / low 3.0 °C, with 5.3 °C (feels like 2.8 °C) at 09:15 and the peak sitting in the 13:00–14:00 hours.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=temperature_2m_max,temperature_2m_min&timezone=Europe%2FSofia
https://wttr.in/Novi+Iskar?format=j1

**Conditions.** Bright and dry through the morning — open-meteo weather code 1 (mainly clear) at 09:15 with 77% humidity, wttr.in reporting "Sunny", +6 °C, 80% humidity and a 4 km/h wind; cloud thickens to overcast from about 15:00 and stays that way overnight.

**Precipitation.** Only 0.7 mm today and it is all evening: 0.1 mm at 20:00, 0.4 mm at 21:00, 0.2 mm at 22:00, on 58–68% hourly probability. Tomorrow goes much wetter and then sharply colder — 1.6 mm, peak probability 73%, high 14.7 °C collapsing to −0.4 °C overnight, with 24 Nov holding dry at 2.5 °C / −3.7 °C.
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=precipitation_sum,precipitation_probability_max,temperature_2m_max,temperature_2m_min&timezone=Europe%2FSofia
https://wttr.in/Novi+Iskar

**Air & daylight.** US AQI 51 ("moderate") at 09:00 local, on PM2.5 9.8 µg/m³, PM10 10.6 µg/m³, ozone 49.0 µg/m³, NO₂ 3.6 µg/m³; 9 h 32 min of daylight between sunrise 07:25 and sunset 16:57, with a max UV index of 2.6.
https://air-quality-api.open-meteo.com/v1/air-quality?latitude=42.7382&longitude=23.5975&current=us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide&timezone=Europe%2FSofia

Flags:
- Evening rain is a single-provider signal: open-meteo tags today with daily code 61 (light rain) and 0.7 mm, while wttr.in's hourly table shows 0.0 mm in every slot today and only a 16% chance at 21:00.
- Warm-side disagreement: today's high 12.0 °C (open-meteo) vs 13 °C (wttr.in); tomorrow 14.7 °C vs 12 °C.
- The barometers look contradictory but are not measuring the same thing — 940.9 hPa from open-meteo is station pressure at the grid point's 670 m elevation, 1020 hPa from wttr.in is sea-level reduced. Do not compare them.
- Tomorrow's precipitation type is genuinely contested: wttr.in calls 18:00 on 23 Nov "Moderate snow" (0.1 mm), open-meteo keeps code 80 (rain showers) all day and does not go sub-zero until after midnight.
- Caveat: both providers cycle their models several times a day, so the 20:00–23:00 rain band and the 24 Nov cold snap (−3.7 °C overnight) are the least stable numbers here; re-check late this afternoon.
