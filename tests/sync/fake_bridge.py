"""Stand-in for bridge/run.mjs speaking the same JSON-lines protocol. Never touches a network.

The request's username (OneZero: email) picks the behaviour: ok | otp | wrong | crash | garbage | hang | leak.
"""

import json
import os
import sys
import time


def send(obj):
    print(json.dumps(obj), flush=True)


req = json.loads(sys.stdin.readline())
creds = req["credentials"]
mode = creds.get("username") or creds.get("email")  # email: OneZero
# Credentials must arrive on stdin only.
secret = creds.get("password", "")
if len(secret) >= 6 and (
    any(secret in a for a in sys.argv) or any(secret in v for v in os.environ.values())
):
    mode = "leak"
if "DEBUG" in os.environ:
    mode = "leak"

send({"type": "progress", "stage": "START_SCRAPING"})
send({"type": "progress", "stage": "LOGGING_IN"})
if mode == "otp":
    send({"type": "otp_request"})
    msg = json.loads(sys.stdin.readline())
    if msg != {"type": "otp", "code": "123456"}:
        send({"type": "result", "success": False, "errorType": "INVALID_OTP"})
        sys.exit(0)
    token = "fresh-token"  # what run.mjs adds after an SMS login (OneZero)
elif mode == "wrong":
    send({"type": "progress", "stage": "LOGIN_FAILED"})
    send(
        {
            "type": "result",
            "success": False,
            "errorType": "INVALID_PASSWORD",
            "errorMessage": "Login failed with INVALID_PASSWORD error",
        }
    )
    sys.exit(0)
elif mode == "crash":
    print("boom: chrome not found", file=sys.stderr, flush=True)
    sys.exit(3)
elif mode == "garbage":
    print("this is not json", flush=True)
    time.sleep(30)
elif mode == "hang":
    time.sleep(30)
elif mode == "leak":
    send({"type": "result", "success": False, "errorType": "GENERAL_ERROR", "errorMessage": "leak"})
    sys.exit(0)

send({"type": "progress", "stage": "LOGIN_SUCCESS"})
send(
    {
        "type": "result",
        **({"freeriseOtpLongTermToken": token} if mode == "otp" else {}),
        "success": True,
        "accounts": [
            {
                "accountNumber": "1234",
                "balance": -100.5,
                "cardFrame": 5000,
                "txns": [
                    {
                        "type": "normal",
                        "status": "completed",
                        "date": "2026-09-30T21:30:00.000Z",
                        "processedDate": "2026-11-01T22:00:00.000Z",
                        "originalAmount": -42.5,
                        "originalCurrency": "ILS",
                        "chargedAmount": -42.5,
                        "description": "קפה",
                        "memo": "",
                        "identifier": "arn1",
                    }
                ],
            }
        ],
    }
)
