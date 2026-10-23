// Runs the pinned package's own Max / Cal fetchData on canned provider responses (stdin JSON)
// and prints what the bridge would send. No browser, no network: page and fetch are stubbed.
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const require = createRequire(new URL('../../bridge/package.json', import.meta.url));
const lib = id => require(`israeli-bank-scrapers/lib/${id}`);
require('moment-timezone').tz.setDefault('Asia/Jerusalem'); // BaseScraper.initialize() does this

const { company, startDate, raw } = JSON.parse(readFileSync(0, 'utf8'));
const options = { companyId: company, startDate: new Date(`${startDate}T00:00:00`), futureMonthsToScrape: 1 };
const json = x => [JSON.stringify(x), 200];
let scraper;

if (company === 'max') {
  scraper = new (lib('scrapers/max').default)(options);
  scraper.page = {
    evaluate: async (_fn, url) => {
      if (url.includes('getCategories')) return json(raw.categories);
      if (url.includes('getHomePageData')) return json(raw.home);
      const month = JSON.parse(new URL(url).searchParams.get('filterData')).date;
      return json({ result: { transactions: raw.months[month] ?? [] } });
    },
  };
} else {
  scraper = new (lib('scrapers/visa-cal').default)(options);
  scraper.page = { evaluate: async (_fn, key) => JSON.stringify(raw.session[key]) };
  globalThis.fetch = async (url, req) => {
    const body = JSON.parse(req.body);
    let resp;
    if (url.includes('GetFrameStatus')) resp = raw.frames[body.cardsForFrameData[0].cardUniqueId];
    else if (url.includes('getClearanceRequests')) resp = raw.pending[body.cardUniqueIDArray[0]];
    else resp = raw.months[`${body.cardUniqueId}:${body.year}-${body.month}`] ?? raw.emptyMonth;
    return { json: async () => resp };
  };
}

const result = await scraper.fetchData();
if (company === 'max') {
  result.freeriseHomePageCards = Object.fromEntries(raw.home.Result.UserCards.Cards.map(c => [c.Last4Digits, c]));
}
process.stdout.write(JSON.stringify({ type: 'result', ...result }));
