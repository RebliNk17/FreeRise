import crypto from 'node:crypto';
import { EventEmitter } from 'node:events';

const IDENTITY_BASE_URL = 'https://sa.pepper.co.il';
const GRAPHQL_API_URL = 'https://fe-sec.pepper.co.il/graphql';
const AID = 'DIGITAL_BLL';
const LOCALE = 'en-US';
const APK_VERSION = '11.11.1';
const APP_VERSION_HEADER = '11.11.1-202610131543';
const TS_CLIENT_VERSION = '8.2.3 (10870);[1,2,3,6,7,8,10,11,12,14,28,19,27]';
const SDK_VERSION_METADATA = '8.2.3 (10870)';
const STATIC_AUTH_HEADER = 'TSToken 7cf2d7a7-681d-450a-ab23-06e48d2b8fd6; tid=digital_client_token_token';
const USER_AGENT = 'okhttp/4.12.0';
const PAGE_SIZE = 100;
const TOKEN_FRESHNESS_MARGIN_SECONDS = 60;

const USER_DATA_V2 = `
query UserDataV2 {
  userDataV2 {
    getUserDataV2 {
      customerAndAccounts {
        customerId
        accounts {
          accountId
          accountNumber
          accountCategory
        }
      }
    }
  }
}
`;

const FETCH_ACCOUNT_BALANCE = `
query fetchAccountBalance($accountId: String!) {
  accounts {
    balance(accountId: $accountId) {
      currentBalance
    }
  }
}
`;

const TRANSACTIONS = `
query Transactions(
  $accountId: String!
  $from: String
  $to: String
  $pageNumber: Int
  $pageCount: Int
) {
  accounts {
    oshTransactionsNew(
      accountId: $accountId
      from: $from
      to: $to
      pageNumber: $pageNumber
      pageCount: $pageCount
    ) {
      totalCount
      transactions {
        transactionId
        transactionAmount
        bookingDate
        effectiveDate
        currency
        description
        title
        subTitle
        referenceNumber
        liquidityStatus
      }
      pendingTransactions {
        transactionId
        transactionAmount
        bookingDate
        effectiveDate
        currency
        description
        title
        subTitle
        referenceNumber
        liquidityStatus
      }
    }
  }
}
`;

const APP_PERMISSIONS = [
  'android.permission.INTERNET',
  'android.permission.ACCESS_NETWORK_STATE',
  'com.google.android.c2dm.permission.RECEIVE',
  'com.google.android.gms.permission.AD_ID',
  'android.permission.RECEIVE_BOOT_COMPLETED',
  'android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS',
  'android.permission.VIBRATE',
  'android.permission.WAKE_LOCK',
  'android.permission.ACCESS_WIFI_STATE',
  'android.permission.DOWNLOAD_WITHOUT_NOTIFICATION',
  'android.permission.ACCESS_ADSERVICES_ATTRIBUTION',
  'android.permission.USE_FINGERPRINT',
  'android.permission.USE_BIOMETRIC',
  'android.permission.READ_PROFILE',
  'android.permission.ACCESS_ADSERVICES_AD_ID',
  'android.permission.FOREGROUND_SERVICE',
  'com.google.android.finsky.permission.BIND_GET_INSTALL_REFERRER_SERVICE',
  'com.google.android.providers.gsf.permission.READ_GSERVICES',
  'com.pepper.ldb.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION',
  'android.permission.NFC',
  'android.permission.USE_FULL_SCREEN_INTENT',
  'android.permission.SCHEDULE_EXACT_ALARM',
  'android.permission.ACCESS_NOTIFICATION_POLICY',
].map(name => ({ name, granted: true }));

function normalizePepperPhone(raw) {
  const digits = String(raw || '').replace(/\D/g, '');
  if (/^05\d{8}$/.test(digits)) {
    return { uid: `972${digits.slice(1)}`, localUserId: digits };
  }
  if (/^9725\d{8}$/.test(digits)) {
    return { uid: digits, localUserId: `0${digits.slice(3)}` };
  }
  return null;
}

function generateEcP256Bundle() {
  const { privateKey, publicKey } = crypto.generateKeyPairSync('ec', { namedCurve: 'P-256' });
  const publicKeyDer = publicKey.export({ type: 'spki', format: 'der' });
  const pkcs8Der = privateKey.export({ type: 'pkcs8', format: 'der' });
  return {
    privateKey,
    publicKeyBase64: publicKeyDer.toString('base64'),
    keyIdHex: crypto.createHash('sha256').update(publicKeyDer).digest('hex'),
    pkcs8Base64: pkcs8Der.toString('base64'),
  };
}

function importEcP256Bundle(pkcs8Base64) {
  try {
    const privateKey = crypto.createPrivateKey({
      key: Buffer.from(pkcs8Base64, 'base64'),
      format: 'der',
      type: 'pkcs8',
    });
    const publicKey = crypto.createPublicKey(privateKey);
    const publicKeyDer = publicKey.export({ type: 'spki', format: 'der' });
    return {
      privateKey,
      publicKeyBase64: publicKeyDer.toString('base64'),
      keyIdHex: crypto.createHash('sha256').update(publicKeyDer).digest('hex'),
      pkcs8Base64,
    };
  } catch {
    return null;
  }
}

function generateRsa2048PublicKeyBase64() {
  const { publicKey } = crypto.generateKeyPairSync('rsa', {
    modulusLength: 2048,
    publicExponent: 0x10001,
  });
  return publicKey.export({ type: 'spki', format: 'der' }).toString('base64');
}

function buildContentSignature(pathAndQuery, bodyJson, ec) {
  const qi = pathAndQuery.indexOf('?');
  const sortedPathAndQuery =
    qi < 0
      ? pathAndQuery
      : `${pathAndQuery.slice(0, qi)}?${pathAndQuery
          .slice(qi + 1)
          .split('&')
          .sort((a, b) => a.localeCompare(b))
          .join('&')}`;
  const escapePart = part => part.split('%%').join('\\%');
  const canonical = [sortedPathAndQuery, TS_CLIENT_VERSION, bodyJson].map(escapePart).join('%%');
  const sigBase64 = crypto
    .sign('sha256', Buffer.from(canonical, 'utf8'), {
      key: ec.privateKey,
      dsaEncoding: 'der',
    })
    .toString('base64');
  return `data:${sigBase64};key-id:${ec.keyIdHex};scheme:4`;
}

function buildCollectionResult(nowMs) {
  return {
    metadata: {
      scheme_version: 2,
      physical_app_id: 'com.pepper.ldb',
      version: SDK_VERSION_METADATA,
      timestamp: Math.floor(nowMs / 1000),
    },
    content: {
      hw_authenticators: {
        device_biometrics: {
          supported: true,
          user_registered: false,
          possible_types: ['fingerprint'],
        },
        fingerprint: { supported: false, user_registered: false },
        face_id: { supported: false, user_registered: false },
      },
      device_details: {
        hw_type: 'Phone',
        tampered: true,
        sim_operator: '310260',
        roaming: false,
        device_model: 'Google/sdk_gphone64_x86_64',
        os_version: '13',
        jailbroken: true,
        security_patch: '2024-03-01',
        sim_operator_name: 'T-Mobile',
        frontal_camera: false,
        device_name: 'e71c2b2f5a0cbd94',
        has_hw_security: false,
        screen_lock: false,
        os_type: 'Android',
        boot_loader: 'unknown',
        base_os: '',
        logged_users: 0,
        persistence_mode: 'false',
        last_reboot: 85993,
        tz: 'GMT',
        sflags: -3,
        supported_abis: ['x86_64'],
        master_key_generated: nowMs,
      },
      app_permissions: APP_PERMISSIONS,
      capabilities: {
        fido2_user_verifying_platform_authenticator_available: false,
        audio_acquisition_supported: true,
        finger_print_supported: false,
        image_acquisition_supported: true,
        persistent_keys_supported: true,
        face_id_key_bio_protection_supported: false,
        fido2_client_present: true,
        dyadic_present: false,
        installed_plugins: [],
        host_provided_features: '19',
      },
      collector_state: {
        accounts: 'active',
        devicedetails: 'active',
        contacts: 'active',
        owner: 'active',
        locationcountry: 'active',
        bluetooth: 'active',
        externalsdkdetails: 'active',
        hwauthenticators: 'active',
        capabilities: 'active',
        largedata: 'active',
        localenrollments: 'active',
        devicefingerprint: 'active',
        apppermissions: 'active',
        software: 'disabled',
        location: 'disabled',
      },
      local_enrollments: {},
    },
  };
}

function isJwtFresh(token) {
  try {
    const [, payloadPart] = String(token || '').split('.');
    if (!payloadPart) return false;
    const payload = JSON.parse(Buffer.from(payloadPart, 'base64url').toString('utf8'));
    if (typeof payload?.exp !== 'number') return false;
    return payload.exp > Math.floor(Date.now() / 1000) + TOKEN_FRESHNESS_MARGIN_SECONDS;
  } catch {
    return false;
  }
}

function encodePersistentState(state) {
  return Buffer.from(JSON.stringify(state), 'utf8').toString('base64url');
}

function decodePersistentState(encoded) {
  try {
    const parsed = JSON.parse(Buffer.from(String(encoded || ''), 'base64url').toString('utf8'));
    if (
      parsed?.v === 1 &&
      typeof parsed.deviceId === 'string' &&
      typeof parsed.clientInstanceId === 'string' &&
      typeof parsed.ecPrivateKeyPkcs8Base64 === 'string' &&
      typeof parsed.token === 'string'
    ) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

function extractHeaderField(headers, key) {
  if (!Array.isArray(headers)) return undefined;
  for (const h of headers) {
    if (typeof h?.[key] === 'string') return h[key];
  }
  return undefined;
}

function extractPasswordAssertionId(data) {
  const methods = data?.control_flow?.[0]?.methods;
  if (!Array.isArray(methods)) return undefined;
  const pwdMethod = methods.find(m => m?.type === 'password');
  return typeof pwdMethod?.assertion_id === 'string' ? pwdMethod.assertion_id : undefined;
}

function extractSmsAssertionId(data) {
  const methods = data?.control_flow?.[0]?.methods;
  if (!Array.isArray(methods)) return undefined;
  for (const method of methods) {
    const channels = method?.channels;
    if (Array.isArray(channels)) {
      const sms = channels.find(ch => ch?.type === 'sms');
      if (typeof sms?.assertion_id === 'string') return sms.assertion_id;
    }
  }
  return undefined;
}

function formatDateIso(d) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export class PepperScraper {
  constructor(options) {
    this.options = options;
    this.emitter = new EventEmitter();
    this.accessToken = undefined;
    this.localUserId = '';
    this.pepperClientId = crypto.randomUUID();
    this.cookies = new Map();
  }

  onProgress(fn) {
    this.emitter.on('SCRAPE_PROGRESS', fn);
  }

  emitProgress(type) {
    this.emitter.emit('SCRAPE_PROGRESS', this.options.companyId, { type });
  }

  updateCookies(response) {
    const setCookies =
      typeof response.headers?.getSetCookie === 'function'
        ? response.headers.getSetCookie()
        : [response.headers?.get?.('set-cookie')].filter(Boolean);
    for (const rawCookie of setCookies) {
      const [pair] = rawCookie.split(';');
      const eqIdx = pair.indexOf('=');
      if (eqIdx > 0) {
        this.cookies.set(pair.slice(0, eqIdx).trim(), pair.slice(eqIdx + 1).trim());
      }
    }
  }

  getCookieHeader() {
    return [...this.cookies.entries()].map(([k, v]) => `${k}=${v}`).join('; ');
  }

  async postTransmit(pathAndQuery, bodyObj, ec) {
    const bodyJson = JSON.stringify(bodyObj);
    const signature = buildContentSignature(pathAndQuery, bodyJson, ec);
    const headers = {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      Authorization: STATIC_AUTH_HEADER,
      'X-TS-Client-Version': TS_CLIENT_VERSION,
      'User-Agent': USER_AGENT,
      'Content-Signature': signature,
    };
    const cookieHeader = this.getCookieHeader();
    if (cookieHeader) {
      headers.Cookie = cookieHeader;
    }
    const response = await fetch(`${IDENTITY_BASE_URL}${pathAndQuery}`, {
      method: 'POST',
      headers,
      body: bodyJson,
    });
    this.updateCookies(response);
    const text = await response.text();
    try {
      return JSON.parse(text);
    } catch {
      throw new Error(
        `sending a request to the institute server returned with status code ${response.status} and a non-JSON body, url: ${IDENTITY_BASE_URL}${pathAndQuery}`,
      );
    }
  }

  async resumeWithSavedState(uid, password, saved) {
    if (isJwtFresh(saved.token)) {
      this.accessToken = saved.token;
      return {
        success: true,
        persistentOtpToken: encodePersistentState(saved),
      };
    }

    const ec = importEcP256Bundle(saved.ecPrivateKeyPkcs8Base64);
    if (!ec) {
      return null; // Fall back to fresh SMS enrollment if otpCodeRetriever is available
    }

    this.cookies.clear();
    const flowId = crypto.randomUUID();
    const nowMs = Date.now();
    const loginPath = `/api/v2/auth/login?aid=${AID}&did=${saved.deviceId}&locale=${LOCALE}&tsm=${nowMs}`;
    const loginResp = await this.postTransmit(
      loginPath,
      {
        headers: [
          { type: 'flow_id', flow_id: flowId },
          { type: 'uid', uid },
        ],
        data: {
          collection_result: buildCollectionResult(nowMs),
          policy_request_id: 'default',
          params: {
            CellPhoneID: saved.clientInstanceId,
            Version_App: APK_VERSION,
            transactionId: crypto.randomUUID(),
          },
        },
      },
      ec,
    );

    const challenge = loginResp?.data?.challenge;
    const pwdAction = loginResp?.data?.control_flow?.[0]?.type || 'authentication';
    const pwdAssertionId = extractPasswordAssertionId(loginResp?.data);
    const sessionId = extractHeaderField(loginResp?.headers, 'session_id');

    if (!challenge || !pwdAssertionId || !sessionId) {
      return null; // Device forgotten by Pepper; fall back to fresh SMS enrollment if available
    }

    const assertMs = Date.now();
    const assertPath = `/api/v2/auth/assert?aid=${AID}&did=${saved.deviceId}&sid=${sessionId}&locale=${LOCALE}&tsm=${assertMs}`;
    const assertResp = await this.postTransmit(
      assertPath,
      {
        headers: [
          { type: 'flow_id', flow_id: flowId },
          { type: 'uid', uid },
        ],
        data: {
          action: pwdAction,
          assert: 'authenticate',
          assertion_id: pwdAssertionId,
          fch: challenge,
          data: { password },
          method: 'password',
        },
      },
      ec,
    );

    const token = assertResp?.data?.token;
    if (!token) {
      return {
        success: false,
        errorType: 'INVALID_PASSWORD',
        errorMessage: assertResp?.error_message || 'Pepper rejected the password',
      };
    }

    this.accessToken = token;
    return {
      success: true,
      persistentOtpToken: encodePersistentState({
        ...saved,
        token,
      }),
    };
  }

  async login(credentials) {
    this.emitProgress('LOGGING_IN');
    const normalized = normalizePepperPhone(credentials.phoneNumber);
    if (!normalized) {
      return {
        success: false,
        errorType: 'GENERIC',
        errorMessage: 'A valid Israeli mobile phone number is required for Pepper',
      };
    }
    this.localUserId = normalized.localUserId;

    if (credentials.otpLongTermToken) {
      const savedState = decodePersistentState(credentials.otpLongTermToken);
      if (savedState) {
        const resumed = await this.resumeWithSavedState(normalized.uid, credentials.password, savedState);
        if (resumed) {
          return resumed;
        }
      } else if (isJwtFresh(credentials.otpLongTermToken)) {
        this.accessToken = credentials.otpLongTermToken;
        return {
          success: true,
          persistentOtpToken: credentials.otpLongTermToken,
        };
      }
    }

    if (typeof credentials.otpCodeRetriever !== 'function') {
      return {
        success: false,
        errorType: 'TWO_FACTOR_RETRIEVER_MISSING',
        errorMessage: 'SMS OTP verification is required to enroll Pepper device',
      };
    }

    this.cookies.clear();
    const ec = generateEcP256Bundle();
    const rsaPublicKeyBase64 = generateRsa2048PublicKeyBase64();
    const clientInstanceId = crypto.randomUUID();
    const flowId = crypto.randomUUID();
    const bindMs = Date.now();

    const bindPath = `/api/v2/auth/bind?aid=${AID}&locale=${LOCALE}&tsm=${bindMs}`;
    const bindResp = await this.postTransmit(
      bindPath,
      {
        headers: [
          { type: 'flow_id', flow_id: flowId },
          { type: 'uid', uid: normalized.uid },
        ],
        data: {
          collection_result: buildCollectionResult(bindMs),
          public_key: { key: ec.publicKeyBase64, type: 'ec' },
          encryption_public_key: { key: rsaPublicKeyBase64, type: 'rsa' },
          params: {
            CellPhoneID: clientInstanceId,
            Version_App: APK_VERSION,
            transactionId: crypto.randomUUID(),
          },
        },
      },
      ec,
    );

    const challenge = bindResp?.data?.challenge;
    const pwdAssertionId = extractPasswordAssertionId(bindResp?.data);
    const sessionId = extractHeaderField(bindResp?.headers, 'session_id');
    const deviceId = extractHeaderField(bindResp?.headers, 'device_id');

    if (!challenge || !pwdAssertionId || !sessionId || !deviceId) {
      return {
        success: false,
        errorType: 'INVALID_PASSWORD',
        errorMessage: bindResp?.error_message || 'Failed to initiate Pepper device bind',
      };
    }

    const pwdMs = Date.now();
    const pwdPath = `/api/v2/auth/assert?aid=${AID}&did=${deviceId}&sid=${sessionId}&locale=${LOCALE}&tsm=${pwdMs}`;
    const pwdResp = await this.postTransmit(
      pwdPath,
      {
        headers: [
          { type: 'flow_id', flow_id: flowId },
          { type: 'uid', uid: normalized.uid },
        ],
        data: {
          action: 'authentication',
          assert: 'authenticate',
          assertion_id: pwdAssertionId,
          fch: challenge,
          data: { password: credentials.password },
          method: 'password',
        },
      },
      ec,
    );

    const smsAssertionId = extractSmsAssertionId(pwdResp?.data);
    if (!smsAssertionId) {
      return {
        success: false,
        errorType: 'INVALID_PASSWORD',
        errorMessage: pwdResp?.error_message || 'Pepper rejected the phone number or password',
      };
    }

    const otpCode = await credentials.otpCodeRetriever();
    if (!otpCode || otpCode === '__OTP_CANCELLED__') {
      return {
        success: false,
        errorType: 'GENERIC',
        errorMessage: 'Two-factor authentication canceled by the user',
      };
    }

    const otpMs = Date.now();
    const otpPath = `/api/v2/auth/assert?aid=${AID}&did=${deviceId}&sid=${sessionId}&locale=${LOCALE}&tsm=${otpMs}`;
    const otpResp = await this.postTransmit(
      otpPath,
      {
        headers: [
          { type: 'flow_id', flow_id: flowId },
          { type: 'uid', uid: normalized.uid },
        ],
        data: {
          action: 'authentication',
          assert: 'authenticate',
          assertion_id: smsAssertionId,
          fch: challenge,
          data: { otp: otpCode },
          method: 'otp',
        },
      },
      ec,
    );

    const token = otpResp?.data?.token;
    if (!token) {
      return {
        success: false,
        errorType: 'INVALID_OTP',
        errorMessage: otpResp?.error_message || 'Pepper rejected the verification code',
      };
    }

    this.accessToken = token;
    return {
      success: true,
      persistentOtpToken: encodePersistentState({
        v: 1,
        deviceId,
        clientInstanceId,
        ecPrivateKeyPkcs8Base64: ec.pkcs8Base64,
        token,
      }),
    };
  }

  async queryGraphql(queryname, query, variables = {}) {
    const response = await fetch(GRAPHQL_API_URL, {
      method: 'POST',
      headers: {
        Accept: 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'User-Agent': USER_AGENT,
        authorization: this.accessToken || '',
        'x-pepper-id': this.pepperClientId,
        'x-user-id': this.localUserId,
        appversion: APP_VERSION_HEADER,
        queryname,
        'x-transaction-id': crypto.randomUUID(),
      },
      body: JSON.stringify({ query, variables }),
    });
    const text = await response.text();
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error(
        `sending a request to the institute server returned with status code ${response.status} and a non-JSON body, url: ${GRAPHQL_API_URL}`,
      );
    }
    if (parsed.errors?.length) {
      throw new Error(parsed.errors[0].message);
    }
    if (!parsed.data) {
      throw new Error(`empty GraphQL data from ${GRAPHQL_API_URL} for ${queryname}`);
    }
    return parsed.data;
  }

  mapTransaction(raw, status) {
    const amount = Number(raw.transactionAmount);
    const currency = raw.currency || 'ILS';
    const description = String(raw.title || raw.description || '').trim();
    return {
      identifier: raw.transactionId || raw.referenceNumber || undefined,
      date: raw.bookingDate,
      processedDate: raw.effectiveDate || raw.bookingDate,
      originalAmount: amount,
      originalCurrency: currency,
      chargedAmount: amount,
      chargedCurrency: currency,
      description,
      memo: raw.subTitle || undefined,
      status,
      type: 'normal',
    };
  }

  async fetchAccountTransactions(account, startDate) {
    let balance;
    try {
      const balanceData = await this.queryGraphql('fetchAccountBalance', FETCH_ACCOUNT_BALANCE, {
        accountId: account.accountId,
      });
      if (typeof balanceData.accounts?.balance?.currentBalance === 'number') {
        balance = balanceData.accounts.balance.currentBalance;
      }
    } catch {}

    const from = formatDateIso(startDate);
    const to = formatDateIso(new Date());
    const txns = [];
    const seenIds = new Set();

    for (let pageNumber = 1; pageNumber <= 50; pageNumber += 1) {
      const txnData = await this.queryGraphql('Transactions', TRANSACTIONS, {
        accountId: account.accountId,
        from,
        to,
        pageNumber,
        pageCount: PAGE_SIZE,
      });
      const osh = txnData.accounts?.oshTransactionsNew;
      const posted = osh?.transactions || [];
      const pending = osh?.pendingTransactions || [];

      if (pageNumber === 1) {
        for (const raw of pending) {
          const mapped = this.mapTransaction(raw, 'pending');
          const key = mapped.identifier ? `pending:${mapped.identifier}` : '';
          if (!key || !seenIds.has(key)) {
            if (key) seenIds.add(key);
            txns.push(mapped);
          }
        }
      }

      for (const raw of posted) {
        const mapped = this.mapTransaction(raw, 'completed');
        const key = mapped.identifier ? `posted:${mapped.identifier}` : '';
        if (!key || !seenIds.has(key)) {
          if (key) seenIds.add(key);
          txns.push(mapped);
        }
      }

      const totalCount = osh?.totalCount ?? 0;
      if (posted.length === 0 || posted.length < PAGE_SIZE || pageNumber * PAGE_SIZE >= totalCount) {
        break;
      }
    }

    txns.sort((a, b) => new Date(a.date).valueOf() - new Date(b.date).valueOf());
    return {
      accountNumber: account.accountNumber || account.accountId,
      balance,
      txns,
    };
  }

  async fetchData() {
    if (!this.accessToken) {
      return { success: false, errorType: 'GENERIC', errorMessage: 'login() was not called' };
    }
    const minStart = new Date(Date.now() - 364 * 86400 * 1000);
    const requestedStart = this.options.startDate || minStart;
    const effectiveStart = requestedStart > minStart ? requestedStart : minStart;

    const userData = await this.queryGraphql('UserDataV2', USER_DATA_V2);
    const customers = userData.userDataV2?.getUserDataV2?.customerAndAccounts || [];
    const discovered = customers.flatMap(c => c.accounts || []);
    const supported = discovered.filter(
      acct => !acct.accountCategory || !String(acct.accountCategory).trim() || acct.accountCategory === 'Ils',
    );
    const accounts = await Promise.all(supported.map(acct => this.fetchAccountTransactions(acct, effectiveStart)));
    return {
      success: true,
      accounts,
    };
  }

  async scrape(credentials) {
    this.emitProgress('INITIALIZING');
    this.emitProgress('START_SCRAPING');
    let loginResult;
    try {
      loginResult = await this.login(credentials);
    } catch (e) {
      loginResult = { success: false, errorType: 'GENERIC', errorMessage: e?.message || String(e) };
    }
    let scrapeResult;
    if (loginResult.success) {
      try {
        scrapeResult = await this.fetchData();
      } catch (e) {
        scrapeResult = { success: false, errorType: 'GENERIC', errorMessage: e?.message || String(e) };
      }
    } else {
      scrapeResult = loginResult;
    }
    this.emitProgress('TERMINATING');
    this.emitProgress('END_SCRAPING');
    return scrapeResult;
  }
}
