The core loop is a Lambda that regularly polls `https://www.nytimes.com/puzzles/leaderboards`
for data, and writes it to a Dynamo table. The static site queries data from the DDB
(via `/api/get_data`), and graphs it with [Chart.js](https://www.chartjs.org/docs/latest/).

The site/API is implemented by a two-layer Lambda infrastructure:
* If the path starts with `/api/`, the external Lambda delegates to the inner Lambda
* Else, the external Lambda fetches and serves the appropriate object from an S3 bucket

The userscript `nt-cookie-update.user.js` intercepts the user's cookie for the NYT crossword site,
and stores it in Secrets Manager so that the aforementioned Lambda can reference it.