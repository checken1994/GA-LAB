import os
import importlib
import inspect
from scp.runtime.slm_base import BaseSLM

def load_experts():
    experts = {}
    experts_dir = r'scp\runtime\experts'
    for filename in os.listdir(experts_dir):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = f'scp.runtime.experts.{filename[:-3]}'
            try:
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseSLM) and obj != BaseSLM:
                        # Instantiate to get the domain
                        try:
                            instance = obj()
                            experts[instance.domain] = instance
                            print(f'Loaded {name} for domain {instance.domain}')
                        except Exception as e:
                            pass
            except Exception as e:
                print(f"Failed to load {module_name}: {e}")
    return experts

experts = load_experts()
print(f'Total experts loaded: {len(experts)}')
