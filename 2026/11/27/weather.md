# Weather — Novi Iskar, 27 Nov 2026

Generated 2026-11-27 22:35 Europe/Sofia from an open-meteo run stamped 22:30 local, cross-checked against wttr.in's reading of the same air; a late run, so today is already spent and the forecast that matters is tomorrow's.

**Temperature today.** High 10.3 °C / low 4.0 °C, with 7.1 °C (feels like 5.8 °C) at the 22:30 reference and the peak in the 13:00–14:00 hours; tomorrow tops out at 6.7 °C before the air collapses to a −0.4 °C high on Sunday and a −3.6 °C low (as of 22:30 local).
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,cloud_cover&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code,sunrise,sunset,precipitation_hours,uv_index_max&timezone=Europe%2FSofia&forecast_days=3
https://wttr.in/Novi+Iskar?2nqT

**Conditions.** 100 % cloud cover and WMO code 61 — light rain — at 22:30 with 94 % humidity, a 1.8 km/h wind and 0.10 mm in the 15-minute interval ending there; wttr.in calls the same minute light rain, 7 °C (feels 5 °C), 96 % humidity, 9 km visibility, a 4 km/h ENE wind and 1018 hPa, and credits the day with 0.0 hours of sunshine (as of 22:30 local).
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,cloud_cover&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code,sunrise,sunset,precipitation_hours,uv_index_max&timezone=Europe%2FSofia&forecast_days=3
https://wttr.in/Novi+Iskar?format=j1

**Precipitation.** 4.30 mm fell today across 11 hours, none of it before 13:00 and most of it between 18:00 and 21:00 at 0.7–0.8 mm/h, easing to 0.20 mm/h at the reference hour; tomorrow is the wet one — 21.60 mm spread over all 24 hours at 98–100 % hourly probability, heaviest from 05:00 to 13:00 at 1.1–1.8 mm/h — with 7.90 mm still to come on Sunday (as of 22:30 local model run).
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=precipitation_sum,precipitation_probability_max,weather_code,precipitation_hours&timezone=Europe%2FSofia&forecast_days=3
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&hourly=temperature_2m,precipitation,precipitation_probability,weather_code&timezone=Europe%2FSofia&forecast_days=2
https://wttr.in/Novi+Iskar?2nqT

**The snow line.** The hourly model code flips tomorrow from 61 (rain) to 71 (slight snow) at 18:00, as the hourly temperature crosses 1.2 °C, and makes Sunday code 73 — moderate snow — with a −3.6 °C low; wttr.in has light sleet at tomorrow's midday (+3 °C, feels 0 °C) turning to heavy snow overnight at −1 °C (feels −6 °C) with 17–36 km/h wind and 2 km visibility (as of 22:30 local model run).
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&hourly=temperature_2m,precipitation,precipitation_probability,weather_code&timezone=Europe%2FSofia&forecast_days=2
https://wttr.in/Novi+Iskar?2nqT

**Air & daylight.** US AQI 55 (moderate) at 22:00 with PM2.5 15.8 µg/m³, PM10 16.2 µg/m³, ozone 18.0 µg/m³ and NO₂ 22.3 µg/m³; the sun rose 07:31 and set 16:54 — about 9 h 23 m of daylight — on a maximum UV of 1.60 today and 0.25 tomorrow (as of 22:00 local).
https://air-quality-api.open-meteo.com/v1/air-quality?latitude=42.7382&longitude=23.5975&current=pm2_5,pm10,ozone,nitrogen_dioxide,us_aqi&daily=uv_index_max&timezone=Europe%2FSofia&forecast_days=2
https://api.open-meteo.com/v1/forecast?latitude=42.7382&longitude=23.5975&daily=sunrise,sunset,uv_index_max&timezone=Europe%2FSofia&forecast_days=2

Flags:
- Every weather number here comes from a single 27 November 22:30 local run; a Saturday-morning run will move the snow line and the totals, and tomorrow's brief will disagree with today's in good faith.
- Today's high is 10.3 °C on open-meteo against 9 °C on wttr.in, whose midday slot reads 9 °C with patchy rain — the same air, two numbers.
- wttr.in's 1018 hPa is a sea-level reduction and open-meteo's grid for Novi Iskar sits at 670 m with no station pressure in the block used here — the two are not the same measurement and are not compared.
- The 21.60 mm is one open-meteo model run; wttr.in gives 1.4 mm in tomorrow's midday slot and 0.9 mm overnight, an order of magnitude apart on totals rather than a rounding difference.
- Tomorrow's wind and visibility are wttr.in's alone; this run's open-meteo request carried no hourly wind, so the blowing-snow picture has one provider behind it.
- The air-quality block is stamped 22:00, half an hour behind the 22:30 forecast block beside it, and the two are separate model products, so read the hour as approximate.
