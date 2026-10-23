// One israeli-bank-scrapers run for the FreeRise sync worker (src/freerise/sync/ibs.py).
//
// Protocol, JSON lines:
//   stdin  <- {companyId, credentials, startDate: "YYYY-MM-DD", futureMonths?, screenshotPath?}
//             then, only after we asked, {"type":"otp","code":"..."}
//   stdout -> {"type":"progress","stage":<ScraperProgressTypes>}
//             {"type":"otp_request"}
//             {"type":"result", ...ScraperScrapingResult, freeriseHomePageCards?, freeriseOtpLongTermToken?}
// stdout carries protocol lines only; diagnostics go to stderr. Credentials, OTP codes and the
// proxy URL are never printed.
import { createInterface } from 'node:readline';
import { createScraper } from 'israeli-bank-scrapers';

console.log = console.info = console.debug = console.error; // keep stdout protocol-only

const send = obj => new Promise(resolve => process.stdout.write(`${JSON.stringify(obj)}\n`, resolve));
const stdinLines = createInterface({ input: process.stdin })[Symbol.asyncIterator]();
async function readMessage() {
  const { value, done } = await stdinLines.next();
  if (done) throw new Error('bridge stdin closed');
  return JSON.parse(value);
}

const CHROME =
  process.env.FREERISE_CHROME_PATH ||
  (process.platform === 'darwin'
    ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    : '/opt/google/chrome/chrome');
const MAX_HOME_PAGE_DATA = 'https://www.max.co.il/api/registered/getHomePageData';

// Same as the vendored engine's Playwright launch: in the container we run as root.
const BASE_ARGS = process.getuid?.() === 0 ? ['--no-sandbox', '--disable-dev-shm-usage'] : [];

function proxyOptions() {
  const raw = process.env.FREERISE_SCRAPER_PROXY;
  if (!raw) return { args: BASE_ARGS };
  const u = new URL(raw);
  const auth = u.username
    ? { username: decodeURIComponent(u.username), password: decodeURIComponent(u.password) }
    : null;
  return { args: [...BASE_ARGS, `--proxy-server=${u.protocol}//${u.host}`], auth };
}

async function main() {
  const req = await readMessage();
  const proxy = proxyOptions();
  // freerise patch: Max idle cards. The package builds Max accounts from transactions only; the
  // home-page card list it already fetches is captured (passively, no extra request) so the
  // Python side can add cards with no transactions, as the vendored engine does.
  let homePageCards;
  const options = {
    companyId: req.companyId,
    // Local midnight; the worker runs us with TZ=Asia/Jerusalem.
    startDate: new Date(`${req.startDate}T00:00:00`),
    futureMonthsToScrape: req.futureMonths ?? 1,
    combineInstallments: false,
    executablePath: CHROME,
    args: proxy.args,
    storeFailureScreenShotPath: req.screenshotPath || undefined,
    preparePage: async page => {
      if (proxy.auth) await page.authenticate(proxy.auth);
      if (req.companyId === 'max') {
        page.on('response', response => {
          if (response.url() !== MAX_HOME_PAGE_DATA) return;
          homePageCards = response.json().then(
            body => body?.Result?.UserCards?.Cards ?? [],
            e => console.error(`home page data unreadable: ${e.message}`),
          );
        });
      }
    },
  };
  const credentials = {
    ...req.credentials,
    otpCodeRetriever: async () => {
      await send({ type: 'otp_request' });
      const msg = await readMessage();
      if (msg.type !== 'otp') throw new Error('expected an otp message');
      return msg.code;
    },
  };
  const scraper = createScraper(options);
  scraper.onProgress((_companyId, { type }) => send({ type: 'progress', stage: type }));
  // Instance-level wraps (the package calls this.login / this.getLongTermTwoFactorToken).
  let otpToken;
  const login = scraper.login.bind(scraper);
  scraper.login = async creds => {
    const r = await login(creds);
    if (r?.success) {
      // API scrapers (OneZero) never report this stage; FreeRise tells login from fetch failures by it.
      await send({ type: 'progress', stage: 'LOGIN_SUCCESS' });
      // OneZero: the long-term token, when it came from a fresh SMS code; FreeRise stores it.
      if (r.persistentOtpToken && r.persistentOtpToken !== req.credentials.otpLongTermToken) {
        otpToken = r.persistentOtpToken;
      }
    }
    return r;
  };
  if (req.companyId === 'oneZero') {
    // A rejected code leaves no resultData; upstream then fails later with an opaque TypeError.
    const verify = scraper.getLongTermTwoFactorToken.bind(scraper);
    scraper.getLongTermTwoFactorToken = async code => {
      const r = await verify(code).catch(e => {
        if (e instanceof TypeError) return null;
        throw e;
      });
      return r?.longTermTwoFactorAuthToken
        ? r
        : { success: false, errorType: 'INVALID_OTP', errorMessage: 'OneZero rejected the verification code' };
    };
  }
  let result;
  try {
    result = await scraper.scrape(credentials);
  } catch (e) {
    // initialize() (browser launch) runs outside the package's own error handling.
    result = { success: false, errorType: 'GENERAL_ERROR', errorMessage: `${e?.name}: ${e?.message}` };
  }
  const cards = await homePageCards;
  if (cards) {
    result.freeriseHomePageCards = Object.fromEntries(
      cards.map(c => [c.Last4Digits, { Last4Digits: c.Last4Digits, CreditLimit: c.CreditLimit, OpenToBuy: c.OpenToBuy, CycleSummary: c.CycleSummary }]),
    );
  }
  if (otpToken) result.freeriseOtpLongTermToken = otpToken;
  await send({ type: 'result', ...result });
}

main().then(
  () => process.exit(0),
  async e => {
    console.error(`bridge failed: ${e?.name}`);
    await send({ type: 'result', success: false, errorType: 'GENERAL_ERROR', errorMessage: `bridge: ${e?.message}` });
    process.exit(1);
  },
);
