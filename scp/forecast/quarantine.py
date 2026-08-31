# -*- coding: utf-8 -*-
"""P2: Forecast Quarantine.
Intercepts forecasts, ensuring hash contracts, probabilities, and evidence.
"""
class ForecastQuarantine:
    def intercept(self, forecast: dict) -> bool:
        if "hash_contract" not in forecast or "probability" not in forecast:
            return False
        if "outcome_evidence" not in forecast or "adjudicator" not in forecast:
            return False
        return True