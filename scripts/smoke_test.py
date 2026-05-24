#!/usr/bin/env python3
"""
Deployment smoke test — run after deploy to verify all critical paths.

Usage:
    python scripts/smoke_test.py --url https://your-app.onrender.com
    python scripts/smoke_test.py --url http://localhost:8000   # local
    python scripts/smoke_test.py --url http://localhost:8000 --full  # include write tests
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any


BASE_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""
    duration_ms: float = 0.0


@dataclass
class SmokeTestRunner:
    base_url: str
    full: bool = False
    results: list[TestResult] = field(default_factory=list)

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
    ) -> tuple[int, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=BASE_HEADERS, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                body_bytes = resp.read()
                try:
                    return status, json.loads(body_bytes)
                except Exception:
                    return status, body_bytes.decode()
        except urllib.error.HTTPError as e:
            body_bytes = e.read()
            try:
                return e.code, json.loads(body_bytes)
            except Exception:
                return e.code, body_bytes.decode()
        except Exception as e:
            return 0, str(e)

    def run(self, name: str, method: str, path: str, body: dict | None = None,
            expect_status: int | list[int] | None = 200,
            check_keys: list[str] | None = None) -> bool:
        t0 = time.perf_counter()
        status, resp_body = self._request(method, path, body)
        elapsed = (time.perf_counter() - t0) * 1000

        if expect_status is None:
            # Accept any 4xx
            passed = 400 <= status < 500
        elif isinstance(expect_status, list):
            passed = status in expect_status
        else:
            passed = status == expect_status
        detail = f"HTTP {status}"

        if passed and check_keys:
            if isinstance(resp_body, dict):
                missing = [k for k in check_keys if k not in resp_body]
                if missing:
                    passed = False
                    detail += f" — missing keys: {missing}"
            else:
                passed = False
                detail += f" — expected dict, got {type(resp_body).__name__}"

        if not passed and isinstance(resp_body, (dict, str)):
            detail += f" | {str(resp_body)[:200]}"

        result = TestResult(name=name, passed=passed, detail=detail, duration_ms=elapsed)
        self.results.append(result)

        status_icon = "PASS" if passed else "FAIL"
        print(f"  [{status_icon}] {name:<55} {detail} ({elapsed:.0f}ms)")
        return passed

    def print_summary(self) -> bool:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        print()
        print("=" * 70)
        print(f"Smoke Test Results: {passed}/{total} passed", end="")
        if failed:
            print(f"  ({failed} FAILED)")
        else:
            print("  ALL PASS")
        print("=" * 70)

        if failed:
            print("\nFailed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  [FAIL] {r.name}: {r.detail}")

        return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Smoke test deployed app")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--full", action="store_true", help="Include write/mutation tests")
    args = parser.parse_args()

    runner = SmokeTestRunner(base_url=args.url, full=args.full)

    print(f"\nSmoke testing: {args.url}")
    print("=" * 70)

    # ------------------------------------------------------------------ #
    # 1. Core health                                                        #
    # ------------------------------------------------------------------ #
    print("\n[1] Core Health")
    runner.run("GET /", "GET", "/", check_keys=["status", "version"])
    runner.run("GET /health", "GET", "/health", check_keys=["status"])

    # ------------------------------------------------------------------ #
    # 2. Lead management endpoints                                          #
    # ------------------------------------------------------------------ #
    print("\n[2] Lead Management")
    runner.run("GET /leads", "GET", "/leads", check_keys=None)  # returns list
    runner.run("GET /leads-scored", "GET", "/leads-scored", expect_status=[200, 503])
    runner.run("GET /leads-scored?tier=hot", "GET", "/leads-scored?tier=hot", expect_status=[200, 503])
    runner.run("GET /leads-scored?tier=warm", "GET", "/leads-scored?tier=warm", expect_status=[200, 503])
    runner.run("GET /leads/999 (non-existent -> 404)", "GET", "/leads/999", expect_status=404)

    # ------------------------------------------------------------------ #
    # 3. Dashboard                                                          #
    # ------------------------------------------------------------------ #
    print("\n[3] Dashboard")
    runner.run("GET /dashboard (HTML)", "GET", "/dashboard", check_keys=None)

    # ------------------------------------------------------------------ #
    # 4. Copilot endpoints                                                  #
    # ------------------------------------------------------------------ #
    print("\n[4] Knowledge Copilot")
    runner.run(
        "POST /copilot/query",
        "POST",
        "/copilot/query",
        body={"query": "What is TRESA?", "jurisdiction": "ontario"},
        expect_status=[200, 503],  # 503 if no DB/OpenAI configured
    )
    runner.run(
        "POST /copilot/query (empty query -> 422 or 503)",
        "POST",
        "/copilot/query",
        body={"query": ""},
        expect_status=[422, 503],
    )

    # ------------------------------------------------------------------ #
    # 5. Webhook endpoints (verify they accept but don't process)          #
    # ------------------------------------------------------------------ #
    print("\n[5] Webhook Endpoints")
    # Meta verification challenge
    runner.run(
        "GET /webhooks/meta (no token -> 403)",
        "GET",
        "/webhooks/meta",
        expect_status=403,
    )
    # Twilio SMS — requires valid sig but endpoint should exist
    runner.run(
        "POST /webhooks/twilio/sms (endpoint exists)",
        "POST",
        "/webhooks/twilio/sms",
        body={"Body": "test", "From": "+16471234567"},
        expect_status=[400, 401, 403, 422, 503],  # any rejection is fine
    )

    # ------------------------------------------------------------------ #
    # 6. Full write tests (--full only)                                    #
    # ------------------------------------------------------------------ #
    if runner.full:
        print("\n[6] Write Tests (--full)")

        # Create a test lead via Retell webhook simulation
        test_call_payload = {
            "event": "call_ended",
            "call": {
                "call_id": f"smoke_test_{int(time.time())}",
                "from_number": "+16471110001",
                "to_number": "+16471110002",
                "start_timestamp": int(time.time() - 120) * 1000,
                "end_timestamp": int(time.time()) * 1000,
                "transcript": (
                    "Agent: Hi, this is the real estate assistant. Are you still "
                    "looking for a home in Brampton?\n"
                    "User: Yes I am. We need a detached home around 900k. We want "
                    "a basement suite for income. Pre-approved already.\n"
                    "Agent: Great! How soon are you looking?\n"
                    "User: Within 2 months ideally."
                ),
                "call_status": "ended",
                "metadata": {"lead_phone": "+16471110001", "lead_name": "Smoke Test Lead"},
            },
        }
        runner.run(
            "POST /webhooks/retell (test call)",
            "POST",
            "/webhooks/retell",
            body=test_call_payload,
            expect_status=200,
        )

        # Give worker a moment
        time.sleep(2)

        # Verify lead was created
        status, resp = runner._request("GET", "/leads?limit=5")
        if status == 200 and isinstance(resp, dict):
            leads = resp.get("leads", [])
            smoke_lead = next((l for l in leads if "Smoke" in (l.get("name") or "")), None)
            if smoke_lead:
                lead_id = smoke_lead["id"]
                runner.results.append(TestResult(
                    name="Retell webhook created lead",
                    passed=True,
                    detail=f"Lead ID={lead_id} score={smoke_lead.get('readiness_score', '?')}",
                ))
                print(f"  v {'Retell webhook created lead':<55} Lead ID={lead_id} ({smoke_lead.get('readiness_score', '?')} score)")

                # Test home fit report on that lead
                runner.run(
                    f"POST /leads/{lead_id}/home-fit-report",
                    "POST",
                    f"/leads/{lead_id}/home-fit-report",
                    body={
                        "buyer_profile": {
                            "name": "Smoke Test Lead",
                            "budget_max": 900000,
                            "basement_income_interest": True,
                            "parking_needed": 2,
                            "bedrooms_needed": 4,
                        }
                    },
                    check_keys=["lead_id", "total_score", "dimensions"],
                )

                # Test lead profile
                runner.run(
                    f"GET /leads/{lead_id}/profile",
                    "GET",
                    f"/leads/{lead_id}/profile",
                    check_keys=["id", "readiness_score", "readiness_tier"],
                )
            else:
                runner.results.append(TestResult(
                    name="Retell webhook created lead",
                    passed=False,
                    detail="Lead not found in /leads after webhook call",
                ))
                print(f"  X Retell webhook created lead — not found in leads list")

    # ------------------------------------------------------------------ #
    # Results                                                               #
    # ------------------------------------------------------------------ #
    all_passed = runner.print_summary()

    if not all_passed:
        print("\nDeployment checklist:")
        print("  • DATABASE_URL set in Render env?")
        print("  • OPENAI_API_KEY set?")
        print("  • TWILIO_* vars set?")
        print("  • RETELL_API_KEY / RETELL_AGENT_ID_EN set?")
        print("  • META_VERIFY_TOKEN / META_APP_SECRET / META_ACCESS_TOKEN set?")
        print("  • See docs/DEPLOYMENT.md for full checklist")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
