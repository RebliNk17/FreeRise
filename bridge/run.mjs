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
import crypto from 'node:crypto';
import https from 'node:https';
import { createInterface } from 'node:readline';
import zlib from 'node:zlib';
import { createScraper } from 'israeli-bank-scrapers';
import { PepperScraper } from './pepper.mjs';

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
const CAL_LOGIN_ENDPOINT = 'https://connect.cal-online.co.il/col-rest/calconnect/authentication/login';
const CAL_LOGIN_SITE_ID = '5B5160DD-F84A-4D72-B67E-65891BA194FF';
const CAL_INIT_ENDPOINT = 'https://api.cal-online.co.il/Authentication/api/account/init';
const CAL_INVALID_PASSWORD_MSG = 'שם המשתמש או הסיסמה שהוזנו שגויים';
const CAL_MOBILE_BASE_URL = 'https://api-cc.cal-online.co.il';
const CAL_MOBILE_SITE_ID = '8D37DF16-5812-4ACD-BAE7-CD1A5BFA2207';
const CAL_MOBILE_DEVICE_UUID = crypto.randomBytes(8).toString('hex');
const CAL_MOBILE_HEADERS = {
  Accept: 'application/json',
  'Content-Type': 'application/json; charset=UTF-8',
  'X-Site-Id': CAL_MOBILE_SITE_ID,
  'X-Device': JSON.stringify({
    appVersion: '6.26.17',
    deviceLanguage: 'he',
    manufacturer: 'Google',
    model: 'Pixel 3',
    osVersion: '30',
    platform: 'android',
    timeZoneInGMT: 'GMT+2',
    udid: CAL_MOBILE_DEVICE_UUID,
    uuid: CAL_MOBILE_DEVICE_UUID,
  }),
  platform: 'android',
  version: '6.26.17',
  'User-Agent':
    'Mozilla/5.0 (Linux; Android 11; Pixel 3 Build/RQ1A.210105.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/83.0.4103.120 Mobile Safari/537.36',
};
const FALLBACK_CHROME_MAJOR_VERSION = '127';

// Masks automation fingerprints (navigator.webdriver, matching sec-ch-ua headers)
// to prevent bot-detection/Cloudflare blocks (e.g. on Amex, Cal).
async function maskBrowserAutomation(page) {
  try {
    const browserVersion = await page.browser().version();
    const chromeMajorVersion = browserVersion.match(/Chrome\/(\d+)/)?.[1] ?? FALLBACK_CHROME_MAJOR_VERSION;
    const userAgent =
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      `(KHTML, like Gecko) Chrome/${chromeMajorVersion}.0.0.0 Safari/537.36`;

    await page.setUserAgent(userAgent);
    await page.setExtraHTTPHeaders({
      'sec-ch-ua':
        `"Chromium";v="${chromeMajorVersion}", "Not)A;Brand";v="99", ` + `"Google Chrome";v="${chromeMajorVersion}"`,
      'sec-ch-ua-mobile': '?0',
      'sec-ch-ua-platform': '"Windows"',
      'accept-language': 'he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7',
    });
    await page.evaluateOnNewDocument(() => {
      Object.defineProperty(navigator, 'webdriver', { get: () => false });
    });
  } catch (e) {
    console.error(`maskBrowserAutomation failed: ${e?.message}`);
  }
}

// Same as the vendored engine's Playwright launch: in the container we run as root.
const BASE_ARGS = process.getuid?.() === 0 ? ['--no-sandbox', '--disable-dev-shm-usage'] : [];

const ONE_ZERO_COMPRESSED_CERT = [
  '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',
].join('');

const ONE_ZERO_CIPHERS = [
  '@SECLEVEL=0',
  'TLS_AES_128_GCM_SHA256',
  'TLS_AES_256_GCM_SHA384',
  'TLS_CHACHA20_POLY1305_SHA256',
  'ECDHE-ECDSA-AES128-GCM-SHA256',
  'ECDHE-ECDSA-AES256-GCM-SHA384',
  'ECDHE-ECDSA-CHACHA20-POLY1305',
  'ECDHE-RSA-AES128-GCM-SHA256',
  'ECDHE-RSA-AES256-GCM-SHA384',
  'ECDHE-RSA-CHACHA20-POLY1305',
  'ECDHE-RSA-AES128-SHA',
  'ECDHE-RSA-AES256-SHA',
  'AES128-GCM-SHA256',
  'AES256-GCM-SHA384',
  'AES128-SHA',
  'AES256-SHA',
].join(':');

const ONE_ZERO_SIGALGS = [
  'ecdsa_secp256r1_sha256',
  'rsa_pss_rsae_sha256',
  'rsa_pkcs1_sha256',
  'ecdsa_secp384r1_sha384',
  'rsa_pss_rsae_sha384',
  'rsa_pkcs1_sha384',
  'rsa_pss_rsae_sha512',
  'rsa_pkcs1_sha512',
  'rsa_pkcs1_sha1',
].join(':');

const ONE_ZERO_SECURE_OPTIONS = 0x10 | (crypto.constants.SSL_OP_NO_ENCRYPT_THEN_MAC || 0x80000);
const ONE_ZERO_USER_AGENT = 'ONEZEROIL/4.7.0(564) Lokalize/0 (Android 11 ; Pixel 3) MTLS';

function isOneZeroIdToken(token) {
  try {
    const [, payloadPart] = String(token || '').split('.');
    if (!payloadPart) return false;
    return JSON.parse(Buffer.from(payloadPart, 'base64url').toString('utf8'))?.tokenType === 'idToken';
  } catch {
    return false;
  }
}

function installOneZeroMtlsFetch(onIdToken, onIdentityError) {
  if (Function.prototype.toString.call(globalThis.fetch).includes('stub: no route for')) {
    return; // tests/sync/onezero_stub.mjs preloaded its own fetch stub
  }
  const clientCert = JSON.parse(zlib.inflateRawSync(Buffer.from(ONE_ZERO_COMPRESSED_CERT, 'base64')).toString('utf8'));
  const origFetch = globalThis.fetch;

  globalThis.fetch = async (rawUrl, init = {}) => {
    const url = String(rawUrl).replace('https://identity.tfd-bank.com/v1//', 'https://identity.tfd-bank.com/v1/');
    if (!url.includes('.tfd-bank.com')) {
      return origFetch(rawUrl, init);
    }
    const body = typeof init.body === 'string' ? init.body : '';
    if (url.endsWith('/getIdToken') && body) {
      try {
        const parsedReq = JSON.parse(body);
        if (isOneZeroIdToken(parsedReq.otpSmsToken)) {
          const shortCircuit = { resultData: { idToken: parsedReq.otpSmsToken } };
          return {
            status: 200,
            ok: true,
            text: async () => JSON.stringify(shortCircuit),
            json: async () => shortCircuit,
          };
        }
      } catch {}
    }

    const { status, text } = await new Promise((resolve, reject) => {
      const req = https.request(
        url,
        {
          method: init.method || 'POST',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': ONE_ZERO_USER_AGENT,
            ...(init.headers || {}),
            'Content-Length': Buffer.byteLength(body),
          },
          ciphers: ONE_ZERO_CIPHERS,
          sigalgs: ONE_ZERO_SIGALGS,
          ecdhCurve: 'X25519:P-256:P-384',
          minVersion: 'TLSv1.2',
          maxVersion: 'TLSv1.3',
          ALPNProtocols: ['http/1.1'],
          requestOCSP: true,
          secureOptions: ONE_ZERO_SECURE_OPTIONS,
          ...clientCert,
        },
        res => {
          const chunks = [];
          res.on('data', c => chunks.push(c));
          res.on('error', reject);
          res.on('end', () => resolve({ status: res.statusCode ?? 0, text: Buffer.concat(chunks).toString('utf8') }));
        },
      );
      req.on('error', reject);
      req.setTimeout(30_000, () => req.destroy(new Error(`request to ${url} timed out after 30000ms`)));
      req.end(body);
    });

    return {
      status,
      ok: status >= 200 && status < 300,
      text: async () => text,
      json: async () => {
        let parsed;
        try {
          parsed = JSON.parse(text);
        } catch {
          throw new Error(
            `sending a request to the institute server returned with status code ${status} and a non-JSON body, url: ${url}`,
          );
        }
        if (url.endsWith('/getIdToken') && parsed?.resultData?.idToken) {
          onIdToken(parsed.resultData.idToken);
        }
        if ((url.endsWith('/getIdToken') || url.endsWith('/sessions/token')) && !parsed?.resultData) {
          onIdentityError(parsed?.errorResponse?.type || parsed?.errorCode || 'OneZero authentication failed');
        }
        return parsed;
      },
    };
  };
}

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
  let calTokenPromise;
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
      await maskBrowserAutomation(page);
      if (req.companyId === 'max') {
        page.on('response', response => {
          if (response.url() !== MAX_HOME_PAGE_DATA) return;
          homePageCards = response.json().then(
            body => body?.Result?.UserCards?.Cards ?? [],
            e => console.error(`home page data unreadable: ${e.message}`),
          );
        });
      }
      if (req.companyId === 'visaCal') {
        page.on('response', response => {
          if (response.url().includes('/calconnect/authentication/login') && response.request().method() === 'POST') {
            calTokenPromise = response
              .json()
              .then(data => {
                if (data?.token) scraper.authorization = `CALAuthScheme ${String(data.token).trim()}`;
                return scraper.authorization;
              })
              .catch(() => null);
          }
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
  const scraper = req.companyId === 'pepper' ? new PepperScraper(options) : createScraper(options);
  scraper.onProgress((_companyId, { type }) => send({ type: 'progress', stage: type }));
  // Instance-level wraps (the package calls this.login / this.getLongTermTwoFactorToken).
  let otpToken;
  let mintedIdToken;
  let lastIdentityError;
  if (req.companyId === 'oneZero') {
    installOneZeroMtlsFetch(
      idt => {
        mintedIdToken = idt;
      },
      err => {
        lastIdentityError = err;
      },
    );
  }
  if (req.companyId === 'visaCal') {
    // freerise patch: Cal pure-HTTP API (`api-cc.cal-online.co.il`) + web fallback.
    // Authenticates directly against `https://api-cc.cal-online.co.il/Authentication/api/login/regularLogin`
    // (or `/Authentication/api/login/bioLogin` when a long-term `hash` is stored in `otpLongTermToken`)
    // without launching Chrome, falling back to the web flow only if the mobile endpoint is unreachable.
    const useMobileCal = process.env.FREERISE_CAL_USE_MOBILE_API !== '0';
    let calDirectError = null;
    let calMobileTokenGuid = '';
    let usingMobileCal = false;
    let browserInitialized = false;
    const origCalFetch = globalThis.fetch.bind(globalThis);
    globalThis.fetch = (input, init = {}) => {
      const url = typeof input === 'string' ? input : input?.url || String(input);
      if (usingMobileCal && url.startsWith('https://api.cal-online.co.il/')) {
        const mobileUrl = url
          .replace('https://api.cal-online.co.il/', `${CAL_MOBILE_BASE_URL}/`)
          .replace('/Frames/api/Frames/GetFrameStatus', '/Frames/api/Frames/GetTotalFrameStatus');
        return origCalFetch(mobileUrl, {
          ...init,
          headers: {
            ...CAL_MOBILE_HEADERS,
            Authorization: scraper.authorization,
          },
        });
      }
      return origCalFetch(input, init);
    };

    const mobileCalLogin = async creds => {
      if (!useMobileCal) return false;
      try {
        let data = null;
        if (creds.otpLongTermToken) {
          const bioRes = await fetch(`${CAL_MOBILE_BASE_URL}/Authentication/api/login/bioLogin`, {
            method: 'POST',
            headers: CAL_MOBILE_HEADERS,
            body: JSON.stringify({ hash: creds.otpLongTermToken }),
          }).catch(() => null);
          if (bioRes?.ok) {
            const parsed = await bioRes.json().catch(() => null);
            if (parsed?.statusCode === 1 && parsed?.result?.calConnectToken) {
              data = parsed;
            }
          }
        }
        if (!data) {
          const res = await fetch(`${CAL_MOBILE_BASE_URL}/Authentication/api/login/regularLogin`, {
            method: 'POST',
            headers: CAL_MOBILE_HEADERS,
            body: JSON.stringify({
              username: creds.username,
              password: creds.password,
              uuid: crypto.randomUUID().replace(/-/g, ''),
              newPassword: null,
            }),
          });
          if (res.ok) {
            data = await res.json().catch(() => null);
          }
        }
        if (data?.statusCode === 1 && data?.result?.calConnectToken) {
          scraper.authorization = `CALAuthScheme ${String(data.result.calConnectToken).trim()}`;
          calMobileTokenGuid = data.result.temporaryGuid ?? '';
          if (data.result.hash) {
            mintedIdToken = data.result.hash;
          }
          usingMobileCal = true;
          calDirectError = null;
          return true;
        }
        if (data?.statusCode === 4) {
          calDirectError = 'INVALID_PASSWORD';
          return false;
        }
      } catch {}
      return false;
    };

    const origInitialize = scraper.initialize.bind(scraper);
    const origTerminate = scraper.terminate.bind(scraper);
    const origLogin = scraper.login.bind(scraper);
    scraper.initialize = async () => {
      if (useMobileCal) {
        await send({ type: 'progress', stage: 'INITIALIZING' });
        return;
      }
      browserInitialized = true;
      return origInitialize();
    };
    scraper.terminate = async success => {
      if (!browserInitialized) {
        await send({ type: 'progress', stage: 'TERMINATING' });
        return;
      }
      return origTerminate(success);
    };
    scraper.getXSiteId = async () => (usingMobileCal ? CAL_MOBILE_SITE_ID : '09031987-273E-2311-906C-8AF85B17C8D9');
    scraper.login = async creds => {
      if (useMobileCal) {
        await send({ type: 'progress', stage: 'LOGGING_IN' });
        if (await mobileCalLogin(creds)) {
          return { success: true };
        }
        if (calDirectError === 'INVALID_PASSWORD') {
          return { success: false, errorType: 'INVALID_PASSWORD' };
        }
        browserInitialized = true;
        await origInitialize();
      }
      return origLogin(creds);
    };

    const directCalLogin = async creds => {
      if (scraper.authorization) return true;
      for (let attempt = 0; attempt < 2; attempt++) {
        if (attempt > 0) await new Promise(r => setTimeout(r, 1500));
        try {
          const res = await fetch(CAL_LOGIN_ENDPOINT, {
            method: 'POST',
            headers: {
              Accept: 'application/json, text/plain, */*',
              'Content-Type': 'application/json',
              Origin: 'https://connect.cal-online.co.il',
              Referer: 'https://connect.cal-online.co.il/regular-login',
              'User-Agent':
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
              'X-Site-Id': CAL_LOGIN_SITE_ID,
            },
            body: JSON.stringify({
              username: creds.username,
              password: creds.password,
              recaptcha: '',
            }),
          });
          const text = await res.text();
          if (res.ok) {
            const data = JSON.parse(text);
            if (data?.token) {
              scraper.authorization = `CALAuthScheme ${String(data.token).trim()}`;
              calDirectError = null;
              return true;
            }
          } else if (text.includes(CAL_INVALID_PASSWORD_MSG)) {
            calDirectError = 'INVALID_PASSWORD';
          } else if (text.includes('להחליף סיסמה') || text.includes('הגיע הזמן לסיסמה חדשה')) {
            calDirectError = 'CHANGE_PASSWORD';
          }
        } catch {}
      }
      return false;
    };
    const isInvalidCalUrl = url => {
      try {
        const decoded = decodeURIComponent(url);
        return decoded.includes('/calconnect/error') && decoded.includes(CAL_INVALID_PASSWORD_MSG);
      } catch {
        return false;
      }
    };
    const origGetLoginOptions = scraper.getLoginOptions.bind(scraper);
    scraper.getLoginOptions = creds => {
      const opts = origGetLoginOptions(creds);
      delete opts.userAgent;
      const origInvalidChecks = opts.possibleResults.INVALID_PASSWORD || [];
      const origChangeChecks = opts.possibleResults.CHANGE_PASSWORD || [];
      opts.possibleResults.SUCCESS = [
        ...(opts.possibleResults.SUCCESS || []),
        async () => Boolean(scraper.authorization),
      ];
      opts.possibleResults.INVALID_PASSWORD = [
        async ({ page }) => {
          if (page?.frames().some(f => isInvalidCalUrl(f.url()))) return true;
          for (const check of origInvalidChecks) {
            if (typeof check === 'function' && (await check({ page }).catch(() => false))) return true;
          }
          return calDirectError === 'INVALID_PASSWORD';
        },
      ];
      opts.possibleResults.CHANGE_PASSWORD = [
        async ({ page }) => {
          for (const check of origChangeChecks) {
            if (typeof check === 'function' && (await check({ page }).catch(() => false))) return true;
          }
          return calDirectError === 'CHANGE_PASSWORD';
        },
      ];
      const origPreAction = opts.preAction;
      opts.preAction = async () => {
        if (await directCalLogin(creds)) {
          opts.fields = [];
          opts.submitButtonSelector = async () => {};
          return scraper.page;
        }
        return origPreAction();
      };
      const origPostAction = opts.postAction;
      opts.postAction = async () => {
        if (scraper.authorization) return;
        try {
          await origPostAction();
          if (!scraper.authorization && calTokenPromise) await calTokenPromise;
        } catch (e) {
          if (calTokenPromise) await calTokenPromise;
          if (!scraper.authorization) await directCalLogin(creds);
          if (scraper.authorization || calDirectError) return;
          if (scraper.page?.frames().some(f => isInvalidCalUrl(f.url()))) return;
          throw e;
        }
        if (!scraper.authorization) await directCalLogin(creds);
      };
      return opts;
    };
    const origGetCards = scraper.getCards.bind(scraper);
    scraper.getCards = async () => {
      if (scraper.authorization) {
        const xSiteId = await scraper.getXSiteId();
        const initUrl = usingMobileCal
          ? `${CAL_MOBILE_BASE_URL}/Authentication/api/account/init`
          : CAL_INIT_ENDPOINT;
        const initHeaders = usingMobileCal
          ? { ...CAL_MOBILE_HEADERS, Authorization: scraper.authorization }
          : {
              Authorization: scraper.authorization,
              'X-Site-Id': xSiteId,
              'Content-Type': 'application/json',
              Origin: 'https://digital-web.cal-online.co.il',
              Referer: 'https://digital-web.cal-online.co.il',
              'User-Agent':
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
            };
        const res = await fetch(initUrl, {
          method: 'POST',
          headers: initHeaders,
          body: JSON.stringify(usingMobileCal ? { tokenGuid: calMobileTokenGuid } : {}),
        }).catch(() => null);
        if (res?.ok) {
          const initData = await res.json().catch(() => null);
          if (initData?.result?.cards) {
            return initData.result.cards.map(({ cardUniqueId, last4Digits }) => ({ cardUniqueId, last4Digits }));
          }
        }
      }
      return origGetCards();
    };
  }
  const login = scraper.login.bind(scraper);
  scraper.login = async creds => {
    let r;
    try {
      r = await login(creds);
    } catch (e) {
      if (e instanceof TypeError && lastIdentityError) {
        return { success: false, errorType: 'INVALID_PASSWORD', errorMessage: lastIdentityError };
      }
      throw e;
    }
    if (r?.success) {
      // API scrapers (OneZero) never report this stage; FreeRise tells login from fetch failures by it.
      await send({ type: 'progress', stage: 'LOGIN_SUCCESS' });
      // OneZero: prefer the 10-year idToken when minted from a fresh SMS OTP; FreeRise stores it.
      const candidateToken = mintedIdToken || r.persistentOtpToken;
      if (candidateToken && candidateToken !== req.credentials.otpLongTermToken) {
        otpToken = candidateToken;
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
