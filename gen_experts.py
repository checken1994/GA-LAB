import os

orphaned_sources = {
    'Weather': 'WeatherDataSource',
    'Finance': 'FinanceDataSource',
    'News': 'NewsAPIDataSource',
    'Aerospace': 'AerospaceDataSource',
    'Architecture': 'ArchitectureDataSource',
    'AudioVideo': 'AudioVideoDataSource',
    'Blockchain': 'BlockchainDataSource',
    'Cartography': 'CartographyDataSource',
    'Crafts': 'CraftsDataSource',
    'Cybersecurity': 'CybersecurityDataSource',
    'DigitalMarketing': 'DigitalMarketingDataSource',
    'Diplomacy': 'DiplomacyDataSource',
    'Ecommerce': 'EcommerceDataSource',
    'Energy': 'EnergyDataSource',
    'Environment': 'EnvironmentDataSource',
    'FoodTech': 'FoodTechDataSource',
    'GenAI': 'GenAIDataSource',
    'Geology': 'GeologyDataSource',
    'Logic': 'LogicDataSource',
    'Oceanography': 'OceanographyDataSource',
    'Psychology': 'PsychologyDataSource',
    'Religion': 'ReligionDataSource',
    'Social': 'SocialDataSource',
    'SpaceMedicine': 'SpaceMedicineDataSource',
    'Tourism': 'TourismDataSource',
    'Transport': 'TransportDataSource',
    'UXUI': 'UXUIDataSource',
}

template = '''from typing import Optional, Any
from scp.runtime.experts.__init__ import Base
from scp.data_sources import {ds_class}
import logging

logger = logging.getLogger("scp.experts.{lower_name}")

class {name}(Base):
    """Domain Expert for {name} using {ds_class}."""

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="{name}", domain="{lower_name}", config=config)
        self._ds = None
        try:
            self._ds = {ds_class}()
        except Exception as e:
            logger.debug(f"{name} {ds_class} init failed: {{e}}")

    def predict(self, question: str) -> Any:
        start = self._start_timer()
        answer = ""
        evidence = {{}}
        
        if self._ds and getattr(self._ds, "enabled", True):
            try:
                result = self._ds.query(question)
                if result and result.get("value"):
                    answer = f"{{result['value']}} (source: {ds_class})"
                    evidence = {{"datasource": "{name}", "raw": result}}
            except Exception as e:
                logger.debug(f"{name} query error: {{e}}")

        resp = self._build_response(answer, 0.85 if answer else 0.1, "DataSource hit" if answer else "No hit", evidence)
        self._end_timer(start, bool(answer))
        return resp
'''

experts_dir = r'scp\runtime\experts'
for name, ds_class in orphaned_sources.items():
    lower_name = name.lower()
    filepath = os.path.join(experts_dir, f"{lower_name}.py")
    # Only write if it doesn't exist or is small to avoid overwriting complex logic if it existed
    if not os.path.exists(filepath) or os.path.getsize(filepath) < 500:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(template.format(name=name, ds_class=ds_class, lower_name=lower_name))
            
print("Created missing expert files.")
