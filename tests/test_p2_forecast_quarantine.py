from __future__ import annotations

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.forecast.quarantine import ForecastQuarantine

class TestP2ForecastQuarantine(unittest.TestCase):
    def setUp(self):
        self.q = ForecastQuarantine()

    def test_forecast_missing_evidence(self):
        forecast = {
            "prediction": "The API will return 500."
        }
        self.assertFalse(self.q.intercept(forecast), "Forecast without hash contract and probability must be quarantined.")

    def test_forecast_valid_evidence(self):
        forecast = {
            "prediction": "The API will return 500.",
            "hash_contract": "abc123hash",
            "probability": 0.95,
            "outcome_evidence": "url_check",
            "adjudicator": "reality_verifier"
        }
        self.assertTrue(self.q.intercept(forecast), "Forecast with valid evidence should pass.")

if __name__ == "__main__":
    unittest.main()