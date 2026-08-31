'\nSCP V104.2 — Fast Learning Engine (CANONICAL — post G3-MERGE)\n==============================================================\n[G3-MERGE] This file is now the SINGLE source of truth for learning.\nThe legacy `real_learning_engine.py` has been reduced to a thin\ncompatibility stub that delegates to this module (see real_learning_engine.py).\nRace condition eliminated: previously, both RealLearningEngine AND\nFastLearningEngine started background threads that wrote to the same KB\n(`data/v13.db`) concurrently → duplicate Ollama calls + interleaved\nSQLite writes. After merge, only ONE engine class exists; the background\nthread starter is idempotent (module-level guard).\n\nTối ưu tốc độ học 10-50x so với V104.1:\n\n1. PARALLEL OLLAMA: 10 concurrent requests (Semaphore 10) — vs tuần tự cũ\n2. SKIP-ALREADY-KNOWN: Skip câu hỏi đã có trong KB → chỉ hỏi câu mới\n3. COMPOUNDING: Mỗi cycle dùng KB đã học để sinh câu hỏi sâu hơn (cấp 2, 3)\n4. ADAPTIVE INTERVAL: 5 min default; nếu facts mới > 50% → 1 min; < 10% → 30 min\n5. BATCH WIKIPEDIA: 5 Wikipedia search concurrent\n\nPLUS (ported from real_learning_engine.py during G3-MERGE):\n- LOOP 1: ollama_learning_cycle() — sequential V104.1 API (kept for /v104/learn/ollama)\n- LOOP 2: local_learning_cycle() — scan data/ files → extract facts → verify → KB\n- LOOP 3: news_learning_cycle() — fetch RSS headlines → verify → KB\n- run_all_cycles() — orchestrate all 3 loops\n- Module constants: SEED_QUESTIONS, COUNTRIES, DOMAINS, COMPOUNDS,\n  COUNTRY_DOMAIN_HINTS,\n  NEWS_SOURCES, LEARNING_INTERVAL\n- Helper funcs: get_country_domain_matrix(), get_total_combinations()\n\nKết quả benchmark dự kiến:\n  V104.1 tuần tự: 10 câu × 2s/câu = 20s\n  V104.2 parallel: 10 câu / 10 concurrent = 2s (10x nhanh hơn)\n\nYêu cầu: LLM gateway (OpenRouter API) đã cấu hình trong .env\n'

from __future__ import annotations

import asyncio

import json

import logging

import os

import random

import re

import sqlite3

import threading

import time

import urllib.parse

import urllib.request

from datetime import datetime

from pathlib import Path

from scp.core.db_manager import _KNOWLEDGE_CANONICAL_DDL

from scp.core.learning_run_ledger import ledger_run

from scp.core.subsystem_telemetry import SubsystemTelemetry, heartbeat_sleep, telemetry_async_cycle

logger = logging.getLogger('scp.core.fast_learning_engine')

SEED_QUESTIONS = {'geography': ['Thủ đô của {country} là gì?', 'Diện tích của {country} bao nhiêu km vuông?', 'Dân số của {country} là bao nhiêu?', 'Sông dài nhất ở {country} tên gì?', 'Đỉnh núi cao nhất ở {country} tên gì?'], 'history': ['{country} độc lập vào năm nào?', 'Ai là người sáng lập {country}?', 'Chiến tranh lớn nhất ở {country} diễn ra khi nào?'], 'chemistry': ['Khoáng sản quan trọng nhất của {country} là gì?', 'Ngành hóa chất lớn nhất ở {country} sản xuất cái gì?', 'Nhiên liệu chính được dùng để phát điện ở {country} là gì?', 'Công thức phân tử của {compound} là gì?', 'Khối lượng phân tử của {compound} là bao nhiêu?', 'Nhiệt độ sôi của {compound} là bao nhiêu độ C?'], 'physics': ['Nhà vật lý học nổi tiếng nhất của {country} là ai?', 'Phát minh vật lý quan trọng nhất của {country} là gì?', 'Trường đại học nghiên cứu vật lý hàng đầu ở {country} tên gì?', 'Tốc độ ánh sáng là bao nhiêu km/s?', 'Hằng số hấp dẫn G có giá trị bao nhiêu?', 'Hằng số Planck có giá trị bao nhiêu?'], 'biology': ['Động vật đặc trưng (đặc hữu) của {country} là con gì?', 'Loài thực vật phổ biến nhất ở {country} là cây gì?', 'Vườn quốc gia lớn nhất ở {country} tên gì?', 'Số nhiễm sắc thể của con người là bao nhiêu?', 'ADN được phát hiện bởi ai?', 'Quang hợp tạo ra khí gì?']}

COUNTRIES = ['Việt Nam', 'Trung Quốc', 'Nhật Bản', 'Hàn Quốc', 'Ấn Độ', 'Nga', 'Mỹ', 'Anh', 'Pháp', 'Đức', 'Brazil', 'Úc', 'Canada', 'Thái Lan']

DOMAINS = ['geography', 'history', 'chemistry', 'physics', 'biology']

COMPOUNDS = ['nước', 'muối ăn', 'axit sunfuric', 'ethanol', 'methane', 'ammoniac']

COUNTRY_DOMAIN_HINTS = {'Việt Nam': {'chemistry': 'khoáng sản: than đá, apatit, boxit', 'physics': 'nhà vật lý: Trần Đại Nghĩa', 'biology': 'đặc hữu: sao la, voọc mũi hếch, rùa Hoàn Kiếm'}, 'Trung Quốc': {'chemistry': 'khoáng sản: đất hiếm, than đá lớn nhất thế giới', 'physics': 'phát minh: la bàn, thuốc súng', 'biology': 'đặc hữu: gấu trúc, cá heo Dương Tử'}, 'Nhật Bản': {'chemistry': 'ngành hóa chất: Sumitomo, Mitsui', 'physics': 'Nobel vật lý: Yukawa Hideki (1949)', 'biology': 'đặc hữu: salamander khổng lồ Nhật Bản, hạc đỏ'}, 'Hàn Quốc': {'chemistry': 'ngành hóa chất: LG Chem, Samsung SDI', 'physics': 'Nobel vật lý: chưa có', 'biology': 'đặc hữu: hổ Siberia (giới hạn), sáo Triều Tiên'}, 'Ấn Độ': {'chemistry': 'khoáng sản: quặng sắt, mica', 'physics': 'Nobel vật lý: C.V. Raman (1930)', 'biology': 'đặc hữu: hổ Bengal, sư tử châu Á, voi Ấn Độ'}, 'Nga': {'chemistry': 'khoáng sản: dầu mỏ, khí tự nhiên, kim cương', 'physics': 'Nobel vật lý: nhiều (Landau, Kapitsa, Ginzburg)', 'biology': 'đặc hữu: hổ Amur, báo tuyết, gấu nâu Kamchatka'}, 'Mỹ': {'chemistry': 'ngành hóa chất: Dow, DuPont, ExxonMobil', 'physics': 'Nobel vật lý: Feynman, Einstein, many', 'biology': 'đặc hữu: đại bàng hói, gấu xám, nai sừng tấm'}, 'Anh': {'chemistry': 'ngành hóa chất: ICI (lịch sử), BP, Shell', 'physics': 'Newton, Faraday, Maxwell, Hawking', 'biology': 'đặc hữu: chim cuồi, hồ Loch Ness (huyền thoại)'}, 'Pháp': {'chemistry': 'khoáng sản: uranium (Artois), muối', 'physics': 'Nobel vật lý: Becquerel, Curie, de Broglie', 'biology': 'đặc hữu: giông Pháp, nai Do ec'}, 'Đức': {'chemistry': 'BASF, Bayer, Bayerische Motoren Werke', 'physics': 'Einstein, Planck, Heisenberg, Born', 'biology': 'đặc hữu: lợn rừng Đức, chim đại bàng vàng'}, 'Brazil': {'chemistry': 'khoáng sản: quặng sắt, nhôm, mangan', 'physics': 'Nobel vật lý: chưa có', 'biology': 'đặc hữu: Amazon — jaguar, anaconda, chim ruồi'}, 'Úc': {'chemistry': 'khoáng sản: quặng sắt, vàng, than đá', 'physics': 'Nobel vật lý: Bragg (cha+con, 1915)', 'biology': 'đặc hữu: kangaroo, koala, platypus, echidna'}, 'Canada': {'chemistry': 'khoáng sản: uranium, kali, vàng', 'physics': 'Nobel vật lý: Strangeway, Brockhouse, McDonald', 'biology': 'đặc hữu: gấu Bắc Cực, nai sừng tấm, beaver'}, 'Thái Lan': {'chemistry': 'khoáng sản: thiếc, wolfram, fluorite', 'physics': 'Nobel vật lý: chưa có', 'biology': 'đặc hữu: voi Thái, gaur, bò tót'}}

def get_country_domain_matrix() -> dict:
    """
    Trả về ma trận 14 quốc gia × 5 lĩnh vực.
    Mỗi cell = số câu hỏi có thể sinh ra.
    """
    matrix = {}
    for country in COUNTRIES:
        matrix[country] = {}
        for domain in DOMAINS:
            templates = SEED_QUESTIONS[domain]
            country_templates = sum((1 for t in templates if '{country}' in t))
            matrix[country][domain] = country_templates
    return matrix

def get_total_combinations() -> int:
    """Tổng số combinations country×field có thể sinh ra = 14 × 5 = 70 cells."""
    matrix = get_country_domain_matrix()
    return sum((sum(cells.values()) for cells in matrix.values()))

NEWS_SOURCES = ['https://rss.nytimes.com/services/xml/rss/nyt/World.xml', 'https://feeds.bbci.co.uk/news/world/rss.xml', 'https://vnexpress.net/rss/the-gioi.rss']

LEARNING_INTERVAL = int(os.environ.get('SCP_LEARNING_INTERVAL', '3600'))

PARALLEL_LLM_CONCURRENCY = int(os.environ.get('SCP_LEARN_CONCURRENCY', '10'))

WIKIPEDIA_CONCURRENCY = int(os.environ.get('SCP_WIKI_CONCURRENCY', '5'))

LEARN_INTERVAL_FAST = int(os.environ.get('SCP_LEARN_INTERVAL_FAST', '300'))

LEARN_INTERVAL_BURST = int(os.environ.get('SCP_LEARN_INTERVAL_BURST', '60'))

LEARN_INTERVAL_IDLE = int(os.environ.get('SCP_LEARN_INTERVAL_IDLE', '1800'))

LEARN_CYCLE_TIMEOUT_SECONDS = int(os.environ.get('SCP_FAST_LEARNING_CYCLE_TIMEOUT_SECONDS', '300'))

SKIP_KNOWN_QUESTIONS = os.environ.get('SCP_SKIP_KNOWN', '1') == '1'

COMPOUNDING_ENABLED = os.environ.get('SCP_COMPOUNDING', '1') == '1'

_FAST_LEARNING_THREAD: threading.Thread | None = None

_FAST_LEARNING_THREAD_LOCK = threading.Lock()

def start_fast_learning_thread(scp_db_path: str='data/v13.db', data_dir: str='data') -> threading.Thread:
    """[G3-MERGE A5] Start V104.2 fast learning thread — adaptive interval.

    IDEMPOTENT: uses module-level _FAST_LEARNING_THREAD guard so calling this
    function multiple times (e.g. once via `start_learning_thread` alias from
    real_learning_engine stub, once via direct `start_fast_learning_thread`
    call in helpers.py:444) will NOT spawn multiple threads writing to the
    same KB. This eliminates the race condition documented in Task 2-B P1-04.
    """
    global _FAST_LEARNING_THREAD
    with _FAST_LEARNING_THREAD_LOCK:
        if _FAST_LEARNING_THREAD is not None and _FAST_LEARNING_THREAD.is_alive():
            logger.info(f"[G3-MERGE A5] start_fast_learning_thread called again but thread '{_FAST_LEARNING_THREAD.name}' is already running — returning existing handle (idempotent guard prevents race condition).")
            return _FAST_LEARNING_THREAD

        def learning_loop():
            time.sleep(30)
            engine = FastLearningEngine(scp_db_path=scp_db_path, data_dir=data_dir, telemetry_subsystem='fast_learning')
            logger.info(f'V104.2 FastLearningEngine started (concurrency={PARALLEL_LLM_CONCURRENCY}, interval={LEARN_INTERVAL_FAST}s adaptive)')
            _consecutive_429 = 0
            while True:
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    engine._telemetry_timeout_requested = True
                    try:
                        results = loop.run_until_complete(asyncio.wait_for(engine.fast_learning_cycle(count=50), timeout=LEARN_CYCLE_TIMEOUT_SECONDS))
                    finally:
                        engine._telemetry_timeout_requested = False
                        loop.close()
                    asked = results.get('asked', 0)
                    verified = results.get('verified', 0)
                    if asked > 0 and verified == 0:
                        _consecutive_429 += 1
                        if _consecutive_429 >= 3:
                            logger.warning(f' {_consecutive_429} consecutive cycles with 0 verified (likely OpenRouter 429) — backing off 10 min')
                            heartbeat_sleep(engine._telemetry, 600, status='IDLE')
                            _consecutive_429 = 0
                            continue
                    else:
                        _consecutive_429 = 0
                    sleep_s = engine.get_adaptive_interval()
                    logger.info(f"V104.2 adaptive sleep: {sleep_s}s (mode={results['adaptive_mode']})")
                    heartbeat_sleep(engine._telemetry, sleep_s, status='IDLE')
                except asyncio.TimeoutError as e:
                    logger.error('V104.2 FastLearning cycle TIMEOUT after %ss: %s', LEARN_CYCLE_TIMEOUT_SECONDS, e)
                    engine._telemetry_timeout_requested = False
                    heartbeat_sleep(engine._telemetry, 60, status='TIMEOUT')
                except Exception as e:
                    logger.error(f'V104.2 fast learning loop error: {e}')
                    if engine._telemetry:
                        engine._telemetry.cycle_failed(f'fast-learning-loop-{time.time_ns()}', e, status='TELEMETRY_DEGRADED')
                    heartbeat_sleep(engine._telemetry, 60, status='TELEMETRY_DEGRADED')
        thread = threading.Thread(target=learning_loop, daemon=True, name='scp-v104-fast-learning')
        thread.start()
        _FAST_LEARNING_THREAD = thread
        return thread

def start_learning_thread(scp_db_path: str='data/v13.db', data_dir: str='data') -> threading.Thread:
    """[G3-MERGE] DEPRECATED alias — delegates to start_fast_learning_thread.

    TẠI SAO: pre-merge, helpers.py:74 imported this name from real_learning_engine
    and called it to start the V104.1 sequential 1-hour thread. That thread
    RACED with start_fast_learning_thread (5-min adaptive) writing to the same
    KB. After merge, both calls resolve to the SAME idempotent function —
    only ONE thread runs. The V104.1 sequential loop is still accessible via
    the FastLearningEngine.run_all_cycles() method (called by /v104/learn/all
    endpoint on demand, NOT in a background thread).
    """
    logger.info('[G3-MERGE] start_learning_thread() called — delegating to start_fast_learning_thread (idempotent). The V104.1 sequential 1-hour thread is DEPRECATED; use /v104/learn/all endpoint for on-demand sequential learning.')
    return start_fast_learning_thread(scp_db_path=scp_db_path, data_dir=data_dir)

if __name__ == '__main__':
    print('=== V104.2 Fast Learning Engine — Test ===\n')
    import tempfile
    tmpdir = tempfile.mkdtemp()
    engine = FastLearningEngine(scp_db_path=os.path.join(tmpdir, 'test.db'), data_dir=tmpdir)

    async def mock_ask_llm_parallel(question):
        await asyncio.sleep(0.1)
        return f'Mock: {question[:50]}'

    async def mock_check_wiki_parallel(question, answer):
        await asyncio.sleep(0.05)
        return {'verified': True, 'confidence': 0.85}
    engine._ask_llm_parallel = mock_ask_llm_parallel
    engine._check_wikipedia_parallel = mock_check_wiki_parallel
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print('Test 1: 10 questions parallel (mocked)...')
    t0 = time.time()
    r1 = loop.run_until_complete(engine.fast_learning_cycle(count=10))
    t1 = time.time()
    print(f'  Time: {(t1 - t0) * 1000:.0f}ms (vs ~2000ms tuần tự)')
    print(f"  Asked: {r1['asked']}, Verified: {r1['verified']}, Stored: {r1['stored']}, Mode: {r1['adaptive_mode']}")
    print('\nTest 2: 50 questions parallel...')
    t0 = time.time()
    r2 = loop.run_until_complete(engine.fast_learning_cycle(count=50))
    t1 = time.time()
    print(f'  Time: {(t1 - t0) * 1000:.0f}ms')
    print(f"  Asked: {r2['asked']}, Skipped: {r2['skipped_known']}, Stored: {r2['stored']}")
    print(f'\nStats: {engine.stats()}')
    loop.close()
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    print('\n✓ Test complete.')

from .fast_learning_engine_parts.fastlearningengine import FastLearningEngine
