# Monthly and annual aggregation

daymet-mcp computes every monthly and annual value from Daymet **daily** data (DOI
10.3334/ORNLDAAC/2129) and labels each series with its aggregation, units and a
machine-readable field label.

| Variable | Daily units | Monthly | Annual | Alternative |
|---|---|---|---|---|
| prcp | mm/day | **sum**, mm/month (`prcp_monthly_total_mm`) | **sum**, mm/year (`prcp_annual_total_mm`) | none |
| tmax | degC | mean, degC (`tmax_monthly_mean_degC`) | mean, degC | none |
| tmin | degC | mean, degC (`tmin_monthly_mean_degC`) | mean, degC | none |
| vp | Pa | mean, Pa (`vp_monthly_mean_Pa`) | mean, Pa | none |
| swe | kg/m2 | mean, kg/m2 (`swe_monthly_mean_kg_m2`) | mean, kg/m2 | `last`: value on the last Daymet day of the period |
| srad | W/m2 (daylight average) | mean of daylight averages, W/m2 (`srad_monthly_mean_W_m2`) | mean of daylight averages, W/m2 | `total`: sum of srad*dayl/1e6, MJ/m2/month or MJ/m2/year |
| dayl | s/day | mean, s/day (`dayl_monthly_mean_s`) | mean, s/day | none |

**Monthly precipitation is a total of daily values (mm/month), never a mean.** This matches
the ORNL monthly product (DOI 10.3334/ORNLDAAC/2131), whose guide defines monthly prcp as
"the total accumulated precipitation over the monthly period", and tmax, tmin, vp and swe as
averages. ORNL publishes no monthly srad or dayl.

**srad is a daylight-period average, not a 24-hour mean.** Daily srad is the shortwave flux
averaged over the `dayl` seconds of daylight, so its monthly and annual means are means of
daylight averages in W/m2. Multiplying a daily value by `dayl/86400` gives that day's 24-hour
mean flux; over a year this is roughly half the daylight average, as mean daylength is near 12 h. For energy per area use the `total` alternative
(MJ/m2), which sums srad x dayl / 1e6 over the period.

## Calendar

Every Daymet year has 365 days. Leap years keep February 29 and drop December 31, so a
leap-year December has 30 days and its prcp total covers December 1-30. The server never
imputes December 31, never rescales sums to a nominal month length, and never fills gaps: a
period with a missing daily value is `complete: false` with value `null`.

## Rounding

Daily values are rounded to 2 decimals (the CSV precision). Aggregates are computed from the
unrounded upstream floats and rounded to 3 decimals.
