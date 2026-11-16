# Citing Daymet data

Daymet data are not covered by daymet-mcp's MIT licence. Cite the dataset DOI for every use,
the single-pixel tool when it was used, and (recommended) the method papers.
`daymet_get_citation` renders the templates below; wording changes need no code.

* Values that daymet-mcp computed (monthly and annual summaries) come from the **daily**
  product, so they cite DOI 10.3334/ORNLDAAC/2129, not the ORNL monthly (2131) or annual
  (2130) products.
* The citation embedded in single-pixel responses adds "B.E. Wilson" as an author; the
  Daymet V4 R1 user guide does not. daymet-mcp uses the user-guide form.
* "All Daymet data are provisional and subject to revision."
* Citation guidance: https://daymet.ornl.gov/citations

## Templates

<!-- template id="daily" role="dataset" requirement="required" doi="10.3334/ORNLDAAC/2129" -->
Thornton, M.M., R. Shrestha, Y. Wei, P.E. Thornton, and S-C. Kao. 2022. Daymet: Daily Surface Weather Data on a 1-km Grid for North America, Version 4 R1. ORNL DAAC, Oak Ridge, Tennessee, USA. https://doi.org/10.3334/ORNLDAAC/2129
```bibtex
@misc{daymet_daily_v4r1,
  author = {Thornton, M. M. and Shrestha, R. and Wei, Y. and Thornton, P. E. and Kao, S-C.},
  title = {Daymet: Daily Surface Weather Data on a 1-km Grid for North America, Version 4 R1},
  publisher = {ORNL DAAC, Oak Ridge, Tennessee, USA},
  year = {2022},
  doi = {10.3334/ORNLDAAC/2129}
}
```
<!-- end -->

<!-- template id="monthly" role="dataset" requirement="required" doi="10.3334/ORNLDAAC/2131" -->
Thornton, M.M., R. Shrestha, Y. Wei, P.E. Thornton, and S-C. Kao. 2022. Daymet: Monthly Climate Summaries on a 1-km Grid for North America, Version 4 R1. ORNL DAAC, Oak Ridge, Tennessee, USA. https://doi.org/10.3334/ORNLDAAC/2131
```bibtex
@misc{daymet_monthly_v4r1,
  author = {Thornton, M. M. and Shrestha, R. and Wei, Y. and Thornton, P. E. and Kao, S-C.},
  title = {Daymet: Monthly Climate Summaries on a 1-km Grid for North America, Version 4 R1},
  publisher = {ORNL DAAC, Oak Ridge, Tennessee, USA},
  year = {2022},
  doi = {10.3334/ORNLDAAC/2131}
}
```
<!-- end -->

<!-- template id="annual" role="dataset" requirement="required" doi="10.3334/ORNLDAAC/2130" -->
Thornton, M.M., R. Shrestha, Y. Wei, P.E. Thornton, and S-C. Kao. 2022. Daymet: Annual Climate Summaries on a 1-km Grid for North America, Version 4 R1. ORNL DAAC, Oak Ridge, Tennessee, USA. https://doi.org/10.3334/ORNLDAAC/2130
```bibtex
@misc{daymet_annual_v4r1,
  author = {Thornton, M. M. and Shrestha, R. and Wei, Y. and Thornton, P. E. and Kao, S-C.},
  title = {Daymet: Annual Climate Summaries on a 1-km Grid for North America, Version 4 R1},
  publisher = {ORNL DAAC, Oak Ridge, Tennessee, USA},
  year = {2022},
  doi = {10.3334/ORNLDAAC/2130}
}
```
<!-- end -->

<!-- template id="single_pixel" role="tool" requirement="required" doi="10.3334/ORNLDAAC/2361" -->
Thornton, M.M., and R. Devarakonda. 2011. Daymet Single Pixel Extraction Tool. ORNL DAAC, Oak Ridge, Tennessee, USA. https://doi.org/10.3334/ORNLDAAC/2361
```bibtex
@misc{daymet_single_pixel,
  author = {Thornton, M. M. and Devarakonda, R.},
  title = {Daymet Single Pixel Extraction Tool},
  publisher = {ORNL DAAC, Oak Ridge, Tennessee, USA},
  year = {2011},
  doi = {10.3334/ORNLDAAC/2361}
}
```
<!-- end -->

<!-- template id="method_2021" role="method" requirement="recommended" doi="10.1038/s41597-021-00973-0" -->
Thornton, P.E., R. Shrestha, M. Thornton, S.-C. Kao, Y. Wei, and B.E. Wilson. 2021. Gridded daily weather data for North America with comprehensive uncertainty quantification. Scientific Data 8:190. https://doi.org/10.1038/s41597-021-00973-0
```bibtex
@article{thornton2021daymet,
  author = {Thornton, P. E. and Shrestha, R. and Thornton, M. and Kao, S.-C. and Wei, Y. and Wilson, B. E.},
  title = {Gridded daily weather data for North America with comprehensive uncertainty quantification},
  journal = {Scientific Data},
  volume = {8},
  pages = {190},
  year = {2021},
  doi = {10.1038/s41597-021-00973-0}
}
```
<!-- end -->

<!-- template id="method_1997" role="method" requirement="recommended" doi="10.1016/S0022-1694(96)03128-9" -->
Thornton, P.E., S.W. Running, and M.A. White. 1997. Generating surfaces of daily meteorological variables over large regions of complex terrain. Journal of Hydrology 190:214-251. https://doi.org/10.1016/S0022-1694(96)03128-9
```bibtex
@article{thornton1997surfaces,
  author = {Thornton, P. E. and Running, S. W. and White, M. A.},
  title = {Generating surfaces of daily meteorological variables over large regions of complex terrain},
  journal = {Journal of Hydrology},
  volume = {190},
  pages = {214--251},
  year = {1997},
  doi = {10.1016/S0022-1694(96)03128-9}
}
```
<!-- end -->

<!-- template id="method_2000" role="method" requirement="recommended" doi="10.1016/S0168-1923(00)00170-2" variables="srad,vp" -->
Thornton, P.E., H. Hasenauer, and M.A. White. 2000. Simultaneous estimation of daily solar radiation and humidity from observed temperature and precipitation: an application over complex terrain in Austria. Agricultural and Forest Meteorology 104:255-271. https://doi.org/10.1016/S0168-1923(00)00170-2
```bibtex
@article{thornton2000radiation,
  author = {Thornton, P. E. and Hasenauer, H. and White, M. A.},
  title = {Simultaneous estimation of daily solar radiation and humidity from observed temperature and precipitation: an application over complex terrain in {Austria}},
  journal = {Agricultural and Forest Meteorology},
  volume = {104},
  pages = {255--271},
  year = {2000},
  doi = {10.1016/S0168-1923(00)00170-2}
}
```
<!-- end -->

<!-- template id="method_1999" role="method" requirement="recommended" doi="10.1016/S0168-1923(98)00126-9" variables="srad,vp" -->
Thornton, P.E., and S.W. Running. 1999. An improved algorithm for estimating incident daily solar radiation from measurements of temperature, humidity, and precipitation. Agricultural and Forest Meteorology 93:211-228. https://doi.org/10.1016/S0168-1923(98)00126-9
```bibtex
@article{thornton1999radiation,
  author = {Thornton, P. E. and Running, S. W.},
  title = {An improved algorithm for estimating incident daily solar radiation from measurements of temperature, humidity, and precipitation},
  journal = {Agricultural and Forest Meteorology},
  volume = {93},
  pages = {211--228},
  year = {1999},
  doi = {10.1016/S0168-1923(98)00126-9}
}
```
<!-- end -->
