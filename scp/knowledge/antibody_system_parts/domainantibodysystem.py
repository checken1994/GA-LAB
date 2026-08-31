# Auto-extracted from antibody_system.py
from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional
from scp.meta.severity import Severity

class DomainAntibodySystem:
    """11 real antibodies với domain filter — chỉ chạy relevant antibodies.

    [Task 7-B] TẠI SAO: clean remove 27 stubs (RC-5 follow-up). Trước đây
    registry khai báo 38 antibodies nhưng 27/38 là stub-fall-through (passed=None
    + warning) → lãng phí CPU + tạo ảo giác "38 antibodies" trong stats endpoint.
    Stub removal KHÔNG break callers (verify: 0 callers reference stub names —
    judge.py + api_server.py chỉ iterate `r.antibody_name` dynamically).

    Naming convention: <Purpose>System (world standard).

    Domain routing:
      "Giá BTC?" → finance → 3 antibodies (pe_ratio, ratio, interest_rate)
      "Thuốc X?" → medical → 1 antibody (dosage)
      "Luật Y?" → legal → 2 antibodies (contract, statute)
      "2+3=?" → math → 0 antibodies (deterministic, no need)
      "Thủ đô?" → geography → 0 antibodies (factual, no need)
      general → 5 antibodies (citation, URL, date, fact, general)
    """
    DOMAIN_ANTIBODY_MAP = {'medical': ['dosage_validator', 'drug_interaction_check'], 'finance': ['pe_ratio_check', 'ratio_validator', 'interest_rate_check'], 'legal': ['contract_check', 'statute_check'], 'geography': ['capital_check'], 'chemistry': ['formula_check'], 'biology': ['abbreviation_check'], 'physics': ['unit_check'], 'history': ['event_date_check'], 'technology': ['http_status_check'], 'general': ['citation_check', 'url_hallucination', 'date_verify', 'fact_check', 'general_check']}
    EXTENDED_DOMAIN_ANTIBODY_MAP = {'economics': ['gdp_check', 'inflation_check'], 'philosophy': ['fallacy_check'], 'psychology': ['cognitive_bias_check'], 'agriculture': ['crop_yield_check'], 'earth_science': ['earthquake_magnitude_check'], 'engineering': ['safety_factor_check', 'material_strength_check'], 'art': ['art_period_check'], 'environmental': ['carbon_emission_check'], 'military': ['weapon_range_check'], 'education': ['pedagogy_check']}

    def __init__(self):
        self._antibody_map: dict[str, dict] = {a['name']: a for a in ANTIBODIES + EXTENDED_ANTIBODIES}
        self._full_domain_antibody_map: dict[str, list[str]] = {**self.DOMAIN_ANTIBODY_MAP, **self.EXTENDED_DOMAIN_ANTIBODY_MAP}
        self._stats = {'total_questions': 0, 'total_antibodies_run': 0, 'total_flags': 0, 'by_domain': {}}

    def should_run(self, antibody_name: str, question: str, domain: str, answer: str='') -> bool:
        """Check if antibody should run for this question + domain.

        2-level filter:
          1. Domain match: antibody domain == question domain (or general)
          2. Keyword match: at least 1 keyword in question OR answer
             (or general with no keywords)

        [ROOT-FIX-11 / Task 32-A] TẠI SAO: antibodies verify ANSWER for
        implausible values (e.g., "8000 MPa" in answer), but should_run()
        only checked QUESTION. If question is "What is steel?" (no "MPa"),
        answer "Steel tensile strength 8000 MPa" never triggered
        material_strength_check. Same for drug_interaction_check (answer
        "warfarin + aspirin") and art_period_check (answer "da Vinci 1503").
        Fix: check keywords in BOTH question AND answer (combined text).
        Backward compat: answer has default "" so old callers still work.
        """
        antibody = self._antibody_map.get(antibody_name)
        if not antibody:
            return False
        ab_domain = antibody.get('domain', 'general')
        if ab_domain != 'general' and ab_domain != domain:
            return False
        keywords = antibody.get('keywords', [])
        if not keywords:
            return True
        combined_text = f'{question} {answer}'.lower()
        import re as _re
        _dosage_units = {'mg', 'g', 'ml', 'mcg', 'µg'}
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in _dosage_units:
                if _re.search('\\d+\\s*' + _re.escape(kw_lower) + '\\b', combined_text):
                    return True
            elif _re.search('\\b' + _re.escape(kw_lower) + '\\b', combined_text):
                return True
        return False

    def get_relevant_antibodies(self, question: str, domain: str, answer: str='') -> list[str]:
        """Get list of antibody names that should run for this question.

        Args:
            question: User question
            domain: Detected domain (medical, finance, legal, ...)
            answer: AI answer to verify (Task 32-A — should_run checks both)

        Returns:
            List of antibody names to run
        """
        relevant = []
        domain_abs = self._full_domain_antibody_map.get(domain, [])
        for ab_name in domain_abs:
            if self.should_run(ab_name, question, domain, answer):
                relevant.append(ab_name)
        for ab_name in self._full_domain_antibody_map.get('general', []):
            if self.should_run(ab_name, question, 'general', answer):
                relevant.append(ab_name)
        return relevant

    def check(self, question: str, answer: str, domain: str='general', ground_truth: Optional[dict[str, Any]]=None) -> list[AntibodyResult]:
        """Run all relevant antibodies for this question.

        Args:
            question: User question
            answer: AI answer to verify
            domain: Detected domain
            ground_truth: Optional ground truth from DataSources

        Returns:
            List of AntibodyResult
        """
        self._stats['total_questions'] += 1
        relevant = self.get_relevant_antibodies(question, domain, answer)
        self._stats['total_antibodies_run'] += len(relevant)
        self._stats['by_domain'][domain] = self._stats['by_domain'].get(domain, 0) + 1
        results = []
        for ab_name in relevant:
            result = self._run_antibody(ab_name, question, answer, domain, ground_truth)
            if result is None:
                raise RuntimeError(f"Antibody '{ab_name}' returned None — stub detected. _run_antibody() must return AntibodyResult.")
            if not hasattr(result, 'passed') or result.passed is None:
                logger.warning(f"Antibody '{ab_name}' returned passed=None — possible stub. Details: {(result.details if hasattr(result, 'details') else 'N/A')}.")
                self._stats['total_stubs_detected'] = self._stats.get('total_stubs_detected', 0) + 1
            results.append(result)
            if not result.passed:
                self._stats['total_flags'] += 1
        return results
    REAL_CHECK_ANTIBODIES = {'citation_check', 'url_hallucination', 'date_verify', 'fact_check', 'dosage_validator', 'pe_ratio_check', 'ratio_validator', 'interest_rate_check', 'contract_check', 'statute_check', 'general_check', 'capital_check', 'formula_check', 'abbreviation_check', 'unit_check', 'event_date_check', 'http_status_check', 'gdp_check', 'inflation_check', 'fallacy_check', 'cognitive_bias_check', 'crop_yield_check', 'earthquake_magnitude_check', 'safety_factor_check', 'material_strength_check', 'drug_interaction_check', 'art_period_check', 'weapon_range_check', 'carbon_emission_check', 'pedagogy_check'}

    def _run_antibody(self, ab_name: str, question: str, answer: str, domain: str, ground_truth: Optional[dict[str, Any]]=None) -> AntibodyResult:
        """Run 1 antibody check."""
        antibody = self._antibody_map[ab_name]
        result = AntibodyResult(antibody_name=ab_name, domain=antibody.get('domain', domain), passed=True, severity=Severity.INFO, confidence=0.5)
        _check_ran = False
        if ab_name == 'citation_check':
            _check_ran = True
            has_claim = any((kw in answer.lower() for kw in ['theo', 'according to', 'nghiên cứu', 'study']))
            has_citation = any((kw in answer.lower() for kw in ['doi', 'http', 'nguồn', 'source:']))
            if has_claim and (not has_citation):
                result.passed = False
                result.severity = 'medium'
                result.confidence = 0.7
                result.details = 'Answer makes claims without citations'
            else:
                result.details = 'Citation check passed: no uncited claims detected'
        elif ab_name == 'url_hallucination':
            _check_ran = True
            urls = re.findall('https?://\\S+', answer)
            bare_domains = re.findall('\\b([a-z0-9-]+\\.(com|org|net|edu|gov|io|ai|co|vn|us|uk|invalid|test|foo|bar))\\b', answer, re.IGNORECASE)
            all_urls = urls + [d[0] for d in bare_domains]
            for url in all_urls:
                if any((s in url.lower() for s in ['example.com', 'example.invalid', 'test.com', 'foo.', 'bar.', 'fake.'])):
                    result.passed = False
                    result.severity = 'high'
                    result.confidence = 0.8
                    result.details = f'Suspicious URL: {url[:60]}'
                    break
                tld = url.split('//')[-1].split('/')[0].split('.')[-1].lower()
                if tld not in ['com', 'org', 'net', 'edu', 'gov', 'io', 'ai', 'co', 'vn', 'us', 'uk']:
                    result.passed = False
                    result.severity = 'medium'
                    result.confidence = 0.6
                    result.details = f'Unusual TLD in URL: {url[:60]}'
            if result.passed:
                result.details = f'URL check passed: {len(all_urls)} URL(s) scanned'
        elif ab_name == 'date_verify':
            _check_ran = True
            future_years = re.findall('\\b(20[3-9]\\d|2[1-9]\\d\\d)\\b', answer)
            if future_years:
                result.passed = False
                result.severity = 'medium'
                result.confidence = 0.7
                result.details = f'Future date(s) in answer: {future_years[:3]}'
            else:
                result.details = 'Date check passed: no future dates'
        elif ab_name == 'fact_check':
            _check_ran = True
            extreme_pct = re.findall('(?:99\\.9%|100%)', answer)
            if extreme_pct:
                result.passed = False
                result.severity = 'low'
                result.confidence = 0.6
                result.details = f'Extreme percentage claim: {extreme_pct}'
            else:
                result.details = 'Fact check passed: no extreme percentages'
        elif ab_name == 'dosage_validator':
            _check_ran = True
            dosage_match = re.findall('(\\d+)\\s*(mg|ml|g|mcg|µg)', answer, re.IGNORECASE)
            for amount, unit in dosage_match:
                amt = int(amount)
                unit_lower = unit.lower()
                if unit_lower == 'mg' and amt > 4000:
                    result.passed = False
                    result.severity = 'high'
                    result.confidence = 0.8
                    result.details = f'Dosage {amt}{unit} exceeds typical max (4000mg paracetamol)'
                elif unit_lower == 'g' and amt > 10:
                    result.passed = False
                    result.severity = 'high'
                    result.confidence = 0.7
                    result.details = f'Dosage {amt}{unit} seems excessive'
                elif unit_lower == 'ml' and amt > 100:
                    result.passed = False
                    result.severity = 'medium'
                    result.confidence = 0.6
                    result.details = f'Volume {amt}{unit} seems excessive for medication'
            if result.passed:
                result.details = f'Dosage check passed: {len(dosage_match)} dosage(s) scanned'
        elif ab_name == 'pe_ratio_check' or ab_name == 'ratio_validator':
            _check_ran = True
            pe_match = re.findall('P/E[^\\d]{0,20}(\\d+(?:\\.\\d+)?)', answer, re.IGNORECASE)
            for pe_str in pe_match:
                pe = float(pe_str)
                if pe < 0 or pe > 500:
                    result.passed = False
                    result.severity = 'medium'
                    result.confidence = 0.7
                    result.details = f'P/E ratio {pe} outside plausible range (0-500)'
            if ab_name == 'ratio_validator':
                ratio_match = re.findall('(\\d+)\\s*:\\s*(\\d+)', answer)
                for num_str, denom_str in ratio_match:
                    num, denom = (float(num_str), float(denom_str))
                    if denom > 0 and (num / denom > 50 or num / denom < 0.01):
                        result.passed = False
                        result.severity = 'medium'
                        result.confidence = 0.7
                        result.details = f'Ratio {num}:{denom} outside plausible range'
            if result.passed:
                result.details = f'Ratio check passed: {len(pe_match)} P/E + ratio(s) scanned'
        elif ab_name == 'interest_rate_check':
            _check_ran = True
            rate_match = re.findall('(\\d+(?:\\.\\d+)?)\\s*%', answer)
            for rate_str in rate_match:
                rate = float(rate_str)
                if rate > 50:
                    result.passed = False
                    result.severity = 'medium'
                    result.confidence = 0.6
                    result.details = f'Interest rate {rate}% seems implausibly high'
            if result.passed:
                result.details = f'Interest rate check passed: {len(rate_match)} rate(s) scanned'
        elif ab_name == 'contract_check':
            _check_ran = True
            if 'penalty' in answer.lower() or 'phạt' in answer.lower():
                penalty_match = re.findall('(\\d+)\\s*%', answer)
                for p_str in penalty_match:
                    p = float(p_str)
                    if p > 20:
                        result.passed = False
                        result.severity = 'medium'
                        result.confidence = 0.6
                        result.details = f'Penalty rate {p}% may be excessive'
            if result.passed:
                result.details = 'Contract check passed: no excessive penalties'
        elif ab_name == 'statute_check':
            _check_ran = True
            q_lower = question.lower()
            a_lower = answer.lower()
            if any((kw in q_lower for kw in ['thời hiệu', 'statute', 'prescription', 'hiệu lực'])):
                years = re.findall('\\b(\\d+)\\s*năm\\b', answer, re.IGNORECASE)
                if not years:
                    years = re.findall('\\b(\\d+)\\s*years?\\b', answer, re.IGNORECASE)
                for y_str in years:
                    y = int(y_str)
                    if y > 30:
                        result.passed = False
                        result.severity = 'low'
                        result.confidence = 0.5
                        result.details = f'Statute of limitations {y} years seems unusually long'
            if result.passed:
                result.details = 'Statute check passed: no unusually long statutes'
        elif ab_name == 'general_check':
            _check_ran = True
            weasel_words = ['hiển nhiên', 'chắc chắn', 'tự nhiên', 'rõ ràng', 'đương nhiên', 'tất nhiên', 'như đã biết', 'như ta đã biết', 'không cần nói', 'quá rõ ràng', 'đã rõ', 'obviously', 'clearly', 'as we know', 'as is well known', 'well known', 'it goes without saying', 'needless to say', 'of course', 'as expected', 'naturally', 'evidently', 'everyone knows', 'as everyone can see', 'plainly', 'as is well-known', 'it is well known']
            for ww in weasel_words:
                if ww in answer.lower():
                    result.passed = False
                    result.severity = 'high'
                    result.confidence = 0.8
                    result.details = f"Closure/weasel word detected: '{ww}'"
                    break
            if result.passed:
                result.details = 'General check passed: no weasel words detected'
        elif ab_name == 'capital_check':
            _check_ran = True
            KNOWN_CAPITALS = {'việt nam': 'hà nội', 'vietnam': 'hà nội', 'hanoi': 'hà nội', 'pháp': 'paris', 'france': 'paris', 'anh': 'london', 'uk': 'london', 'mỹ': 'washington', 'usa': 'washington', 'nhật': 'tokyo', 'japan': 'tokyo', 'trung quốc': 'bắc kinh', 'china': 'beijing', 'nga': 'moscow', 'russia': 'moscow', 'đức': 'berlin', 'germany': 'berlin', 'ý': 'rome', 'italy': 'rome', 'tây ban nha': 'madrid', 'spain': 'madrid', 'úc': 'canberra', 'australia': 'canberra', 'hàn quốc': 'seoul', 'korea': 'seoul', 'ấn độ': 'new delhi', 'india': 'new delhi', 'thái lan': 'bangkok', 'thailand': 'bangkok', 'cam-pu-chia': 'phnom penh'}
            a_lower = answer.lower()
            q_lower = question.lower()
            for country, capital in KNOWN_CAPITALS.items():
                if country in q_lower and capital not in a_lower:
                    result.passed = False
                    result.severity = 'high'
                    result.confidence = 0.8
                    result.details = f"Question asks about '{country}', capital should be '{capital}' but not in answer"
                    break
            if result.passed:
                result.details = 'Capital check passed: no contradictions found'
        elif ab_name == 'formula_check':
            _check_ran = True
            KNOWN_FORMULAS = {'nước': 'h2o', 'water': 'h2o', 'muối': 'nacl', 'salt': 'nacl', 'axit sunfuric': 'h2so4', 'sulfuric acid': 'h2so4', 'axit clohidric': 'hcl', 'hydrochloric acid': 'hcl', 'amoniắc': 'nh3', 'ammonia': 'nh3', 'carbon dioxide': 'co2', 'khí carbonic': 'co2', 'methane': 'ch4', 'metan': 'ch4', 'glucose': 'c6h12o6', 'đường glucose': 'c6h12o6', 'ethanol': 'c2h5oh', 'rượu': 'c2h5oh'}
            a_lower = answer.lower()
            q_lower = question.lower()
            for substance, formula in KNOWN_FORMULAS.items():
                if substance in q_lower and formula not in a_lower:
                    import re as _re
                    formula_match = _re.findall('\\b([A-Z][a-z]?\\d*(?:[A-Z][a-z]?\\d*)+)\\b', answer)
                    if formula_match:
                        result.passed = False
                        result.severity = 'high'
                        result.confidence = 0.8
                        result.details = f"Question asks '{substance}' (formula='{formula}'), but answer has '{formula_match[0]}'"
                        break
            if result.passed:
                result.details = 'Formula check passed: no wrong formulas detected'
        elif ab_name == 'abbreviation_check':
            _check_ran = True
            KNOWN_ABBREVS = {'dna': 'deoxyribonucleic acid', 'rna': 'ribonucleic acid', 'atp': 'adenosine triphosphate', 'adp': 'adenosine diphosphate', 'rbc': 'red blood cell', 'wbc': 'white blood cell', 'mrna': 'messenger rna', 'trna': 'transfer rna', 'rrna': 'ribosomal rna', 'pcr': 'polymerase chain reaction', 'nadh': 'nicotinamide adenine dinucleotide'}
            q_lower = question.lower()
            a_lower = answer.lower()
            for abbr, expansion in KNOWN_ABBREVS.items():
                if abbr in q_lower and expansion not in a_lower:
                    result.passed = False
                    result.severity = 'low'
                    result.confidence = 0.6
                    result.details = f"Question asks '{abbr.upper()}', correct expansion '{expansion}' not in answer"
                    break
            if result.passed:
                result.details = 'Abbreviation check passed: no wrong expansions'
        elif ab_name == 'unit_check':
            _check_ran = True
            import re as _re
            vel_match = _re.findall('(\\d+(?:\\.\\d+)?(?:e[+-]?\\d+)?)\\s*(m/s|km/h|mps|kph)', answer, _re.IGNORECASE)
            for val_str, unit in vel_match:
                val = float(val_str)
                if unit.lower() in ('m/s', 'mps') and val > 300000000.0:
                    result.passed = False
                    result.severity = 'high'
                    result.confidence = 0.9
                    result.details = f'Velocity {val} m/s exceeds speed of light (3e8 m/s)'
                elif unit.lower() in ('km/h', 'kph') and val > 1080000000.0:
                    result.passed = False
                    result.severity = 'high'
                    result.confidence = 0.9
                    result.details = f'Velocity {val} km/h exceeds speed of light'
            temp_match = _re.findall('(\\d+(?:\\.\\d+)?)\\s*(°c|°f|k|kelvin|celsius)', answer, _re.IGNORECASE)
            for val_str, unit in temp_match:
                val = float(val_str)
                if unit.lower() in ('°c', 'celsius') and (val > 6000 or val < -273.15):
                    result.passed = False
                    result.severity = 'medium'
                    result.confidence = 0.8
                    result.details = f'Temperature {val}°C outside plausible range (-273.15 to 6000)'
            if result.passed:
                result.details = 'Physics unit check passed: no implausible values'
        elif ab_name == 'event_date_check':
            _check_ran = True
            KNOWN_EVENTS = {'thế chiến 2': ('1939', '1945'), 'world war 2': ('1939', '1945'), 'ww2': ('1939', '1945'), 'thế chiến 1': ('1914', '1918'), 'world war 1': ('1914', '1918'), 'ww1': ('1914', '1918'), 'cách mạng tháng 10': ('1917', '1917'), 'october revolution': ('1917', '1917'), 'cách mạng pháp': ('1789', '1799'), 'french revolution': ('1789', '1799'), 'moon landing': ('1969', '1969'), 'apollo': ('1969', '1972'), 'berlin wall': ('1989', '1989'), 'tường berlin': ('1989', '1989'), 'vietnam war': ('1955', '1975'), 'chiến tranh việt': ('1955', '1975')}
            q_lower = question.lower()
            a_lower = answer.lower()
            for event, (start, end) in KNOWN_EVENTS.items():
                if event in q_lower:
                    years = re.findall('\\b(1[5-9]\\d{2}|20[0-2]\\d)\\b', answer)
                    for year in years:
                        if int(year) < int(start) - 5 or int(year) > int(end) + 5:
                            result.passed = False
                            result.severity = 'medium'
                            result.confidence = 0.7
                            result.details = f"'{event}' occurred {start}-{end}, but answer mentions {year}"
                            break
                    if not result.passed:
                        break
            if result.passed:
                result.details = 'Event date check passed: no date contradictions'
        elif ab_name == 'http_status_check':
            _check_ran = True
            KNOWN_STATUS = {'200': ('ok', 'success', 'thành công'), '201': ('created', 'tạo'), '204': ('no content', 'không nội dung'), '301': ('moved permanently', 'chuyển vĩnh viễn'), '302': ('found', 'redirect', 'chuyển hướng'), '304': ('not modified', 'không thay đổi'), '400': ('bad request', 'yêu cầu sai'), '401': ('unauthorized', 'không được ủy quyền'), '403': ('forbidden', 'cấm'), '404': ('not found', 'không tìm thấy'), '405': ('method not allowed', 'phương thức không được phép'), '429': ('too many requests', 'quá nhiều yêu cầu'), '500': ('internal server error', 'lỗi server', 'lỗi máy chủ'), '502': ('bad gateway', 'cổng sai'), '503': ('service unavailable', 'dịch vụ không khả dụng'), '504': ('gateway timeout', 'hết thời gian chờ')}
            q_lower = question.lower()
            a_lower = answer.lower()
            status_codes = re.findall('\\b([1-5]\\d{2})\\b', question)
            for code in status_codes:
                if code in KNOWN_STATUS:
                    valid_descs = KNOWN_STATUS[code]
                    if not any((desc in a_lower for desc in valid_descs)):
                        result.passed = False
                        result.severity = 'high'
                        result.confidence = 0.8
                        result.details = f"HTTP {code} should mean '{valid_descs[0]}', but answer doesn't mention it"
                        break
            if result.passed:
                result.details = f'HTTP status check passed: {len(status_codes)} code(s) scanned'
        elif ab_name == 'gdp_check':
            _check_ran = True
            a_lower = answer.lower()
            all_pcts = list(re.finditer('(\\d+(?:\\.\\d+)?)\\s*%', answer))
            for m in all_pcts:
                pct_val = float(m.group(1))
                start = max(0, m.start() - 30)
                end = min(len(a_lower), m.end() + 30)
                context = a_lower[start:end]
                if any((kw in context for kw in ['gdp', 'growth', 'tăng trưởng', 'kinh tế'])):
                    if pct_val > 10:
                        result.passed = False
                        result.severity = 'medium'
                        result.confidence = 0.75
                        result.details = f'GDP growth rate {pct_val}% is implausibly high (most countries grow 0-10%/yr; only China peaked ~14%)'
                        break
            if result.passed:
                result.details = f'GDP check passed: {len(all_pcts)} percentage(s) scanned'
        elif ab_name == 'inflation_check':
            _check_ran = True
            a_lower = answer.lower()
            all_pcts = list(re.finditer('(\\d+(?:\\.\\d+)?)\\s*%', answer))
            for m in all_pcts:
                pct_val = float(m.group(1))
                start = max(0, m.start() - 30)
                end = min(len(a_lower), m.end() + 30)
                context = a_lower[start:end]
                if any((kw in context for kw in ['inflation', 'lạm phát', 'cpi', 'price index'])):
                    if pct_val > 50:
                        result.passed = False
                        result.severity = 'high'
                        result.confidence = 0.85
                        result.details = f'Inflation {pct_val}% — hyperinflation territory. Verify if answer explicitly mentions hyperinflation context.'
                        break
                    elif pct_val > 20:
                        result.passed = False
                        result.severity = 'medium'
                        result.confidence = 0.7
                        result.details = f'Inflation {pct_val}% is extreme — verify against historical data (most countries stay under 20%, except crises)'
                        break
            if result.passed:
                result.details = f'Inflation check passed: {len(all_pcts)} percentage(s) scanned'
        elif ab_name == 'fallacy_check':
            _check_ran = True
            FALLACIES = {'ad hominem': 'attacking the person instead of the argument', 'straw man': "misrepresenting opponent's argument", 'strawman': "misrepresenting opponent's argument", 'false dichotomy': 'presenting only 2 options when more exist', 'false dilemma': 'presenting only 2 options when more exist', 'slippery slope': 'claiming chain reaction without evidence', 'circular reasoning': 'using conclusion as premise', 'begging the question': 'using conclusion as premise', 'appeal to authority': 'using authority as evidence', 'appeal to emotion': 'using emotion instead of evidence', 'post hoc': 'correlation ≠ causation', 'red herring': 'distracting from the argument', 'tu quoque': 'whataboutism / appeal to hypocrisy', 'ngụy biện': 'fallacy detected (Vietnamese)', 'ngụy biện cá nhân': 'ad hominem (Vietnamese)', 'ngụy biện rơm rạ': 'straw man (Vietnamese)', 'lập luận vòng lặp': 'circular reasoning (Vietnamese)'}
            a_lower = answer.lower()
            for fallacy, desc in FALLACIES.items():
                if fallacy in a_lower:
                    result.passed = False
                    result.severity = 'medium'
                    result.confidence = 0.7
                    result.details = f"Logical fallacy detected: '{fallacy}' ({desc}) — answer should identify and refute, not commit fallacies"
                    break
            if result.passed:
                result.details = 'Fallacy check passed: no logical fallacies detected'
        elif ab_name == 'cognitive_bias_check':
            _check_ran = True
            BIASES = {'anchoring bias': 'over-relying on first piece of information', 'confirmation bias': 'favoring info that confirms existing beliefs', 'availability heuristic': 'overweighting easily-recalled examples', 'dunning-kruger': 'low-ability overestimating competence', 'survivorship bias': 'focusing on survivors, ignoring failures', 'sunk cost': 'continuing because of past investment', 'hindsight bias': "'I knew it all along' after the fact", 'framing effect': 'drawing different conclusions from same info', 'bandwagon effect': 'believing because others do', 'halo effect': 'one positive trait coloring overall judgment', 'thiên kiến': 'bias (Vietnamese)', 'thiên kiến xác nhận': 'confirmation bias (Vietnamese)', 'thiên kiến mỏ neo': 'anchoring bias (Vietnamese)', 'thiên lệch': 'bias (Vietnamese)'}
            a_lower = answer.lower()
            for bias, desc in BIASES.items():
                if bias in a_lower:
                    bias_pos = a_lower.find(bias)
                    window = a_lower[max(0, bias_pos - 40):bias_pos + len(bias) + 40]
                    ack_markers = ['avoid', 'recognize', 'aware of', 'fall victim', 'overcome', 'bias toward', 'tránh', 'nhận thức', 'ý thức được']
                    if not any((ack in window for ack in ack_markers)):
                        result.passed = False
                        result.severity = 'low'
                        result.confidence = 0.6
                        result.details = f"Possible cognitive bias in reasoning: '{bias}' ({desc}) — answer uses biased framing without acknowledging it"
                        break
            if result.passed:
                result.details = 'Cognitive bias check passed: no biased reasoning detected'
        elif ab_name == 'crop_yield_check':
            _check_ran = True
            a_lower = answer.lower()
            yield_patterns = ['(\\d+(?:\\.\\d+)?)\\s*(?:tấn|t|tons?)\\s*(?:/|per)?\\s*(?:ha|hectare)', '(\\d+(?:\\.\\d+)?)\\s*(?:tạ)\\s*(?:/|per)?\\s*(?:ha|hectare)']
            checked = 0
            for pattern in yield_patterns:
                for m in re.finditer(pattern, a_lower):
                    val = float(m.group(1))
                    if 'tạ' in pattern:
                        val = val / 10.0
                    checked += 1
                    if val > 15:
                        result.passed = False
                        result.severity = 'medium'
                        result.confidence = 0.75
                        result.details = f'Crop yield {val} t/ha is implausibly high (rice 5-10 t/ha normal; record ~12 t/ha for hybrid rice)'
                        break
                    elif val < 1:
                        result.passed = False
                        result.severity = 'low'
                        result.confidence = 0.6
                        result.details = f'Crop yield {val} t/ha is very low — verify if answer mentions crop failure or specific conditions'
                        break
                if not result.passed:
                    break
            if result.passed:
                result.details = f'Crop yield check passed: {checked} yield(s) scanned'
        elif ab_name == 'earthquake_magnitude_check':
            _check_ran = True
            a_lower = answer.lower()
            mag_patterns = ['magnitude\\s*(?:of|was|is|:|=|scale)?\\s*(\\d+(?:\\.\\d+)?)', '(\\d+(?:\\.\\d+)?)\\s*magnitude', 'mw\\s*(?:of|was|is|:|=)?\\s*(\\d+(?:\\.\\d+)?)', 'ml\\s*(?:of|was|is|:|=)?\\s*(\\d+(?:\\.\\d+)?)', 'richter\\s*(?:scale)?\\s*(?:of|was|is|:|=)?\\s*(\\d+(?:\\.\\d+)?)', 'độ lớn\\s*(?:là|:|=)?\\s*(\\d+(?:\\.\\d+)?)']
            checked = 0
            for pattern in mag_patterns:
                for m in re.finditer(pattern, a_lower):
                    val = float(m.group(1))
                    checked += 1
                    if val > 9.5:
                        result.passed = False
                        result.severity = 'high'
                        result.confidence = 0.85
                        result.details = f'Earthquake magnitude {val} is implausible — largest recorded: 9.5 (Valdivia, Chile 1960)'
                        break
                    elif val < 0:
                        result.passed = False
                        result.severity = 'medium'
                        result.confidence = 0.8
                        result.details = f'Earthquake magnitude {val} is invalid — Richter scale starts at 0 (negative magnitudes impossible)'
                        break
                    elif val > 8:
                        result.passed = False
                        result.severity = 'low'
                        result.confidence = 0.55
                        result.details = f"Earthquake magnitude {val} is in 'great earthquake' range (>8.0) — verify against historical records (rare, ~1/year globally)"
                        break
                if not result.passed:
                    break
            if result.passed:
                result.details = f'Earthquake magnitude check passed: {checked} magnitude(s) scanned'
        elif ab_name == 'safety_factor_check':
            _check_ran = True
            a_lower = answer.lower()
            sf_patterns = ['safety\\s+factor\\s*(?:of|is|=|:|was)?\\s*(\\d+\\.?\\d*)', 'factor\\s+of\\s+safety\\s*(?:of|is|=|:|was)?\\s*(\\d+\\.?\\d*)', 'fos\\s*(?:of|is|=|:|was)?\\s*(\\d+\\.?\\d*)', 'hệ\\s+số\\s+an\\s+toàn\\s*(?:=|:|là)?\\s*(\\d+\\.?\\d*)', 'design\\s+factor\\s*(?:of|is|=|:|was)?\\s*(\\d+\\.?\\d*)']
            checked = 0
            for pattern in sf_patterns:
                for m in re.finditer(pattern, a_lower):
                    val = float(m.group(1))
                    checked += 1
                    if val < 1.0:
                        result.passed = False
                        result.severity = Severity.CRITICAL
                        result.confidence = 0.95
                        result.details = f'Safety factor {val} < 1.0 — structural failure risk (load exceeds capacity)'
                        break
                    elif val > 10:
                        result.passed = False
                        result.severity = Severity.MEDIUM
                        result.confidence = 0.7
                        result.details = f'Safety factor {val} > 10 — over-engineered (suspicious); typical FoS = 1.5-3 for most structures'
                        break
                if not result.passed:
                    break
            if result.passed:
                result.details = f'Safety factor check passed: {checked} value(s) scanned'
        elif ab_name == 'material_strength_check':
            _check_ran = True
            a_lower = answer.lower()
            strength_patterns = [('(\\d+(?:\\.\\d+)?)\\s*gpa', 1000.0), ('(\\d+(?:\\.\\d+)?)\\s*ksi', 6.895), ('(\\d+(?:\\.\\d+)?)\\s*psi', 0.006895), ('(\\d+(?:\\.\\d+)?)\\s*mpa', 1.0)]
            checked = 0
            for pattern, mult in strength_patterns:
                for m in re.finditer(pattern, a_lower):
                    val_mpa = float(m.group(1)) * mult
                    checked += 1
                    if val_mpa > 5000:
                        result.passed = False
                        result.severity = 'medium'
                        result.confidence = 0.75
                        result.details = f'Material strength {val_mpa:.1f} MPa is implausibly high (strongest steels ~2000 MPa; carbon nanotube ~63000 MPa is lab-only)'
                        break
                    elif val_mpa < 10:
                        result.passed = False
                        result.severity = 'low'
                        result.confidence = 0.6
                        result.details = f'Material strength {val_mpa:.1f} MPa is very low for structural use (<10 MPa; concrete ~20-40 MPa minimum)'
                        break
                if not result.passed:
                    break
            if result.passed:
                result.details = f'Material strength check passed: {checked} value(s) scanned'
        elif ab_name == 'drug_interaction_check':
            _check_ran = True
            KNOWN_INTERACTIONS = [({'warfarin', 'aspirin'}, 'bleeding risk (additive anticoagulant effect)', 'high'), ({'warfarin', 'nsaids'}, 'GI bleeding risk', 'high'), ({'warfarin', 'ibuprofen'}, 'GI bleeding risk', 'high'), ({'ssri', 'maoi'}, 'serotonin syndrome (potentially fatal)', 'critical'), ({'fluoxetine', 'maoi'}, 'serotonin syndrome', 'critical'), ({'sertraline', 'maoi'}, 'serotonin syndrome', 'critical'), ({'simvastatin', 'grapefruit'}, 'rhabdomyolysis risk (CYP3A4 inhibition)', 'medium'), ({'atorvastatin', 'grapefruit'}, 'rhabdomyolysis risk', 'medium'), ({'metronidazole', 'alcohol'}, 'disulfiram-like reaction', 'high'), ({'ciprofloxacin', 'theophylline'}, 'theophylline toxicity (CYP1A2 inhibition)', 'medium'), ({'lithium', 'nsaids'}, 'lithium toxicity (reduced renal clearance)', 'high'), ({'ace inhibitor', 'potassium'}, 'hyperkalemia risk', 'medium'), ({'spironolactone', 'potassium'}, 'hyperkalemia risk', 'medium'), ({'tramadol', 'maoi'}, 'serotonin syndrome + seizure risk', 'critical'), ({'clarithromycin', 'statin'}, 'rhabdomyolysis risk', 'high')]
            a_lower = answer.lower()
            found_drugs = set()
            drug_canonical = {'warfarin': 'warfarin', 'aspirin': 'aspirin', 'asa': 'aspirin', 'nsaids': 'nsaids', 'nsaid': 'nsaids', 'ibuprofen': 'ibuprofen', 'ssri': 'ssri', 'ssris': 'ssri', 'maoi': 'maoi', 'maois': 'maoi', 'fluoxetine': 'fluoxetine', 'prozac': 'fluoxetine', 'sertraline': 'sertraline', 'zoloft': 'sertraline', 'simvastatin': 'simvastatin', 'zocor': 'simvastatin', 'atorvastatin': 'atorvastatin', 'lipitor': 'atorvastatin', 'statin': 'statin', 'statins': 'statin', 'grapefruit': 'grapefruit', 'metronidazole': 'metronidazole', 'flagyl': 'metronidazole', 'alcohol': 'alcohol', 'ethanol': 'alcohol', 'ciprofloxacin': 'ciprofloxacin', 'cipro': 'ciprofloxacin', 'theophylline': 'theophylline', 'lithium': 'lithium', 'ace inhibitor': 'ace inhibitor', 'ace inhibitors': 'ace inhibitor', 'potassium': 'potassium', 'spironolactone': 'spironolactone', 'aldactone': 'spironolactone', 'tramadol': 'tramadol', 'ultram': 'tramadol', 'clarithromycin': 'clarithromycin', 'biaxin': 'clarithromycin'}
            for kw, canonical in drug_canonical.items():
                if re.search('\\b' + re.escape(kw) + '\\b', a_lower):
                    found_drugs.add(canonical)
            interaction_found = False
            for pair, desc, sev in KNOWN_INTERACTIONS:
                if pair.issubset(found_drugs):
                    result.passed = False
                    result.severity = sev
                    result.confidence = 0.85
                    result.details = f"Known drug-drug interaction: {' + '.join(sorted(pair))} → {desc}. Answer must explicitly warn about this interaction."
                    interaction_found = True
                    break
            if not interaction_found:
                result.details = f'Drug interaction check passed: {len(found_drugs)} drug(s) detected, no known interactions found'
        elif ab_name == 'art_period_check':
            _check_ran = True
            ARTIST_LIFESPAN = {'leonardo da vinci': (1452, 1519), 'da vinci': (1452, 1519), 'michelangelo': (1475, 1564), 'raphael': (1483, 1520), 'rembrandt': (1606, 1669), 'vermeer': (1632, 1675), 'vangogh': (1853, 1890), 'van gogh': (1853, 1890), 'monet': (1840, 1926), 'renoir': (1841, 1919), 'degas': (1834, 1917), 'cezanne': (1839, 1906), 'cézanne': (1839, 1906), 'picasso': (1881, 1973), 'matisse': (1869, 1954), 'dali': (1904, 1989), 'dalí': (1904, 1989), 'klimt': (1862, 1918), 'warhol': (1928, 1987)}
            STYLE_ERA = {'renaissance': (1400, 1600), 'baroque': (1600, 1750), 'rococo': (1700, 1780), 'neoclassicism': (1760, 1840), 'romanticism': (1780, 1850), 'realism': (1840, 1880), 'impressionism': (1860, 1890), 'post-impressionism': (1880, 1910), 'cubism': (1907, 1925), 'surrealism': (1924, 1966), 'modernism': (1860, 1970), 'gothic': (1150, 1500)}
            a_lower = answer.lower()
            years = re.findall('\\b(1[2-9]\\d{2}|20\\d{2})\\b', answer)
            found_artist = None
            for artist, (birth, death) in ARTIST_LIFESPAN.items():
                if artist in a_lower:
                    found_artist = (artist, birth, death)
                    break
            found_style = None
            for style, (start, end) in STYLE_ERA.items():
                if style in a_lower:
                    found_style = (style, start, end)
                    break
            flagged = False
            for year_str in years:
                year = int(year_str)
                if found_artist:
                    _, birth, death = found_artist
                    if year < birth:
                        result.passed = False
                        result.severity = 'high'
                        result.confidence = 0.85
                        result.details = f"Year {year} is before artist's birth ({birth}) — implausible artwork date"
                        flagged = True
                        break
                    if year > death + 10:
                        result.passed = False
                        result.severity = 'high'
                        result.confidence = 0.85
                        result.details = f"Year {year} is more than 10 years after artist's death ({death}) — implausible artwork date"
                        flagged = True
                        break
                if found_style:
                    style_name, start, end = found_style
                    start_i, end_i = (int(start), int(end))
                    if year < start_i - 5 or year > end_i + 5:
                        result.passed = False
                        result.severity = 'medium'
                        result.confidence = 0.7
                        result.details = f"Year {year} doesn't match {style_name} era (approx. {start}-{end}) — verify attribution"
                        flagged = True
                        break
            if not flagged:
                result.details = f"Art period check passed: {len(years)} year(s) scanned, artist={(found_artist[0] if found_artist else 'unknown')}, style={(found_style[0] if found_style else 'unknown')}"
        elif ab_name == 'weapon_range_check':
            _check_ran = True
            a_lower = answer.lower()
            category = None
            if any((w in a_lower for w in ['handgun', 'pistol', 'súng ngắn'])):
                category = ('handgun', 1.0, 'km')
            elif any((w in a_lower for w in ['rifle', 'súng trường', 'sniper'])):
                category = ('rifle', 3.0, 'km')
            elif any((w in a_lower for w in ['howitzer', 'pháo', 'artillery', 'cannon'])):
                category = ('artillery', 100.0, 'km')
            elif any((w in a_lower for w in ['sam', 'surface-to-air', 'air defense'])):
                category = ('SAM', 500.0, 'km')
            elif any((w in a_lower for w in ['icbm', 'intercontinental', 'tên lửa liên lục địa'])):
                category = ('ICBM', 20000.0, 'km')
            elif any((w in a_lower for w in ['missile', 'tên lửa'])):
                category = ('missile', 10000.0, 'km')
            range_patterns = [('(\\d+(?:\\.\\d+)?)\\s*km\\b', 1.0, 'km'), ('(\\d+(?:\\.\\d+)?)\\s*kilometers?\\b', 1.0, 'km'), ('(\\d+(?:\\.\\d+)?)\\s*(?:m|meters?)\\b', 0.001, 'km'), ('(\\d+(?:\\.\\d+)?)\\s*(?:nm|nautical\\s+miles?)\\b', 1.852, 'km')]
            checked = 0
            flagged = False
            for pattern, mult, _unit in range_patterns:
                for m in re.finditer(pattern, a_lower):
                    val_km = float(m.group(1)) * mult
                    start = max(0, m.start() - 40)
                    end = min(len(a_lower), m.end() + 40)
                    context = a_lower[start:end]
                    if not any((kw in context for kw in ['range', 'tầm', 'reach', 'distance', 'reach', 'fired'])):
                        continue
                    checked += 1
                    if category:
                        cat_name, max_km, _ = category
                        if val_km > max_km:
                            result.passed = False
                            result.severity = 'high'
                            result.confidence = 0.8
                            result.details = f'Weapon range {val_km} km exceeds {cat_name} typical max (~{max_km} km) — verify specification'
                            flagged = True
                            break
                if flagged:
                    break
            if not flagged:
                result.details = f'Weapon range check passed: {checked} range(s) scanned' + (f', category={category[0]}' if category else '')
        elif ab_name == 'carbon_emission_check':
            _check_ran = True
            a_lower = answer.lower()
            is_per_capita = any((kw in a_lower for kw in ['per capita', 'per person', 'người', 'mỗi người']))
            unit_patterns = [('(\\d+(?:,\\d{3})*(?:\\.\\d+)?)\\s*(?:mt|megaton)', 'Mt'), ('(\\d+(?:,\\d{3})*(?:\\.\\d+)?)\\s*(?:gt|gigaton)', 'Gt'), ('(\\d+(?:,\\d{3})*(?:\\.\\d+)?)\\s*(?:kt|kiloton)', 'kt'), ('(\\d+(?:,\\d{3})*(?:\\.\\d+)?)\\s*tons?\\s*(?:co2|carbon)', 'tons'), ('(\\d+(?:,\\d{3})*(?:\\.\\d+)?)\\s*(?:tấn)\\s*(?:co2|carbon)', 'tons'), ('(\\d+(?:,\\d{3})*(?:\\.\\d+)?)\\s*kg\\s*(?:co2|carbon)', 'kg')]
            checked = 0
            flagged = False
            for pattern, unit in unit_patterns:
                for m in re.finditer(pattern, a_lower, re.IGNORECASE):
                    raw = m.group(1).replace(',', '')
                    val = float(raw)
                    checked += 1
                    if unit == 'Gt':
                        val_mt = val * 1000
                    elif unit == 'kt':
                        val_mt = val / 1000
                    elif unit == 'tons':
                        if is_per_capita:
                            if val > 100:
                                result.passed = False
                                result.severity = 'high'
                                result.confidence = 0.85
                                result.details = f'Per capita CO2 emission {val} tons/yr is implausible (global highest: Qatar ~37 tons/yr)'
                                flagged = True
                                break
                            continue
                        else:
                            val_mt = val / 1000000
                    elif unit == 'kg':
                        if is_per_capita:
                            val_tons = val / 1000
                            if val_tons > 100:
                                result.passed = False
                                result.severity = 'high'
                                result.confidence = 0.85
                                result.details = f'Per capita CO2 emission {val_tons:.1f} tons/yr is implausible (global highest: Qatar ~37 tons/yr)'
                                flagged = True
                                break
                        continue
                    else:
                        val_mt = val
                    if not is_per_capita and val_mt > 50000:
                        result.passed = False
                        result.severity = 'high'
                        result.confidence = 0.85
                        result.details = f'CO2 emission {val_mt:.0f} Mt is implausible — global total ~37000 Mt/yr; verify unit/context'
                        flagged = True
                        break
                if flagged:
                    break
            if not flagged:
                result.details = f'Carbon emission check passed: {checked} value(s) scanned' + (', per capita context' if is_per_capita else '')
        elif ab_name == 'pedagogy_check':
            _check_ran = True
            a_lower = answer.lower()
            flagged = False
            PIAGET_STAGES = {'sensorimotor': (0, 2), 'preoperational': (2, 7), 'concrete operational': (7, 11), 'formal operational': (11, 100)}
            if 'piaget' in a_lower:
                for stage, (lo, hi) in PIAGET_STAGES.items():
                    if stage in a_lower:
                        stage_pos = a_lower.find(stage)
                        window = a_lower[max(0, stage_pos - 60):stage_pos + len(stage) + 60]
                        ages = re.findall('(\\d+)\\s*(?:-|\\s+to\\s+)\\s*(\\d+)', window)
                        for age_lo, age_hi in ages:
                            age_lo, age_hi = (int(age_lo), int(age_hi))
                            if age_lo != lo or age_hi != hi:
                                result.passed = False
                                result.severity = 'medium'
                                result.confidence = 0.8
                                result.details = f"Piaget '{stage}' stage is ages {lo}-{hi}, but answer claims {age_lo}-{age_hi}"
                                flagged = True
                                break
                        if flagged:
                            break
                if not flagged:
                    stage_count_claim = re.search('(\\d+)\\s*(?:stages?|giai đoạn)', a_lower)
                    if stage_count_claim:
                        claimed = int(stage_count_claim.group(1))
                        if 'piaget' in a_lower and claimed != 4:
                            result.passed = False
                            result.severity = 'medium'
                            result.confidence = 0.8
                            result.details = f'Piaget has 4 stages, but answer claims {claimed}'
                            flagged = True
            if not flagged and 'bloom' in a_lower:
                BLOOM_LEVELS = {'remember', 'understand', 'apply', 'analyze', 'evaluate', 'create'}
                [lvl for lvl in BLOOM_LEVELS if lvl in a_lower]
                count_claim = re.search('(\\d+)\\s*(?:levels?|cấp độ|tầng)', a_lower)
                if count_claim:
                    claimed = int(count_claim.group(1))
                    if claimed != 6:
                        result.passed = False
                        result.severity = 'medium'
                        result.confidence = 0.8
                        result.details = f"Bloom's revised taxonomy has 6 levels, but answer claims {claimed}"
                        flagged = True
            if not flagged and 'vygotsky' in a_lower:
                if 'zpd' in a_lower or 'zone of proximal development' in a_lower:
                    zpd_pos = max(a_lower.find('zpd'), a_lower.find('zone of proximal development'))
                    if zpd_pos >= 0:
                        window = a_lower[max(0, zpd_pos - 60):zpd_pos + 100]
                        if any((wrong in window for wrong in ['fixed ability', 'innate ability', ' IQ ', 'intelligence quotient'])):
                            result.passed = False
                            result.severity = 'medium'
                            result.confidence = 0.75
                            result.details = 'Vygotsky ZPD is the gap between what a learner can do alone vs with guidance — not a fixed ability or IQ measure'
                            flagged = True
            if not flagged:
                result.details = 'Pedagogy check passed: no misattributed theory claims'
        if not _check_ran:
            if not answer or len(str(answer)) < 3:
                result.passed = False
                result.details = 'Empty or too-short answer'
                result.severity = 'medium'
                result.confidence = 0.7
            else:
                result.passed = None
                result.details = f"stub_not_implemented: antibody '{ab_name}'"
                result.severity = 'warning'
                result.confidence = 0.0
        if _check_ran and ab_name == 'general_check' and (not answer or len(str(answer)) < 3):
            result.passed = False
            result.details = 'Empty or too-short answer'
            result.severity = 'medium'
            result.confidence = 0.7
        return result

    def stats(self) -> dict[str, Any]:
        return {**self._stats, 'total_antibodies': len(ANTIBODIES) + len(EXTENDED_ANTIBODIES), 'avg_per_question': self._stats['total_antibodies_run'] / max(1, self._stats['total_questions'])}
