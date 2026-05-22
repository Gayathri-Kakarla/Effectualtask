Intern task- World Bank macro data project 
This project collects annual macroeconomic data from the World Bank API using a TOML configuration file, reshapes the results into a wide country-indicator panel, and creates a compact summary table for structural-change analysis. 
Project purpose
The goal is to keep the data pipeline fully configuration-driven, so changes to countries, indicators, or the time horizon can be made only in “config.toml” rather than in the Python source code. 
The script downloads annual World Bank indicator data, handles paginated API responses, maps country names to World Bank country codes, preserves missing observations as “NaN”, and exports both a main dataset and a descriptive summary table. 
Configuration
The “config.toml” file controls three things: the country list, the start and end years, and the indicator codes to collect. 
In the current setup, the project requests 17 countries, annual data from 2000 to 2025, and three World Bank indicators: industry value added, manufacturing value added, and real GDP. 
Instructions to run the code:
1. Clone the repository.
2. Install dependencies:
   pip install -r requirements.txt
3. Run the project:
   py run.py
The script will create the output files inside the “output/” folder.
Output files
	“output/worldbank_main_dataset.csv” — the main wide-format dataset with one row per country and indicator, and one column per year from “year_2000” to “year_2025”.
	“output/worldbank_structural_change_summary.csv” — the compact summary table with industry and manufacturing shares plus CAGR fields for each country.

	“output/country_mapping.csv” — the mapping from configured country names to World Bank country codes used in the API calls.
Short Interpretation of the output data
The main dataset contains 51 rows and 28 columns, which matches 17 countries times 3 indicators plus the country, indicator, and yearly columns.
The summary table contains 17 rows, one for each country in the configuration.

Which countries show signs of de-industrialization?
Using the earliest and latest available observations in the dataset, several advanced economies show declining industry and manufacturing shares, which is consistent with de-industrialization in the sense of shrinking value-added shares within GDP.
Countries with the clearest declines in industry share include South Africa, United Kingdom, Mexico, Canada.

Is manufacturing declining faster than total industry?
In most of the data, yes. Manufacturing shares generally fall even more sharply than total industry shares in the same countries, suggesting that manufacturing is often the more rapidly shrinking component of industry within GDP.

Are trends different between advanced and emerging economies?
On average, advanced economies in this sample show an industry-share change of -3.41 percentage points and a manufacturing-share change of -1.01 percentage points between their first and last available observations.
Emerging economies in this sample show an average industry-share change of -3.14 percentage points and a manufacturing-share change of -2.25 percentage points, which suggests a more mixed pattern than in the advanced-economy group.
Overall, manufacturing appears to decline faster than total industry in much of the sample, while emerging economies such as China and Turkey differ from older industrial economies by showing less uniform decline.
Assumptions and limitations
The World Bank API can return missing observations for some country-indicator-year combinations, and the project keeps these missing values explicitly as “NaN” rather than imputing them. 
For the current data pull, 2025 observations are missing for all three indicators in the sample, so the summary file keeps the requested 2025-based share and CAGR fields but many of those values are “NaN”.
This means the interpretation above relies on the earliest and latest available observations in the downloaded data, while the exported summary table follows the assignment's requested column structure exactly.
