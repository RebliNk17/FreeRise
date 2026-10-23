// Preloaded (`node --import`) into the real bridge/run.mjs: stands in for OneZero's API so the
// package's own OneZero flow runs end to end. Any other URL fails: nothing reaches a network.
const now = new Date().toISOString();
const routes = {
  '/devices/token': () => ({ resultData: { deviceToken: 'dev' } }),
  '/otp/prepare': b =>
    b.factorValue === '+972501234567' ? { resultData: { otpContext: 'ctx' } } : { errorCode: 'BadPhone' },
  '/otp/verify': b => (b.otpCode === '123456' ? { resultData: { otpToken: 'fresh-token' } } : { errorCode: 'ErrorOtpCode' }),
  '/getIdToken': b =>
    ['fresh-token', 'stored-token'].includes(b.otpSmsToken) && b.pass === 'pw-onezero'
      ? { resultData: { idToken: 'idt' } }
      : { errorCode: 'Unauthorized' },
  '/sessions/token': () => ({ resultData: { accessToken: 'acc' } }),
  '/graphql': b =>
    b.query.includes('movements')
      ? {
          data: {
            movements: {
              movements: [
                {
                  movementId: 'm1',
                  valueDate: now.slice(0, 10),
                  movementTimestamp: now,
                  movementAmount: '42.5',
                  creditDebit: 'DEBIT',
                  movementCurrency: 'ILS',
                  description: 'קפה',
                  runningBalance: '1000.5',
                },
              ],
              pagination: { cursor: null, hasMore: false },
            },
          },
        }
      : { data: { customer: [{ portfolios: [{ portfolioId: 'p1', portfolioNum: '1234567', accounts: [{ accountId: 'a1' }] }] }] } },
};

globalThis.fetch = async (url, req) => {
  const route = Object.keys(routes).find(k => String(url).endsWith(k));
  if (!route) throw new Error(`stub: no route for ${url}`);
  const body = routes[route](JSON.parse(req.body));
  return { status: 200, json: async () => body };
};
