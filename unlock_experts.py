import os
import re

judge_file = r'scp\runtime\judge.py'
with open(judge_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the empty domain_experts with a real one
new_property = '''
    @property
    def domain_experts(self):
        if not hasattr(self, '_experts'):
            self._experts = {}
            import importlib
            import inspect
            import os
            from scp.runtime.slm_base import BaseSLM
            experts_dir = os.path.join(os.path.dirname(__file__), 'experts')
            for filename in os.listdir(experts_dir):
                if filename.endswith('.py') and filename != '__init__.py':
                    module_name = f'scp.runtime.experts.{filename[:-3]}'
                    try:
                        module = importlib.import_module(module_name)
                        for name, obj in inspect.getmembers(module, inspect.isclass):
                            if issubclass(obj, BaseSLM) and obj != BaseSLM:
                                try:
                                    instance = obj()
                                    self._experts[instance.domain] = instance
                                except Exception:
                                    pass
                    except Exception:
                        pass
        return self._experts
'''

content = re.sub(r'@property\s+def domain_experts\(self\):\s+return\s+\[\]', new_property.strip(), content)

# Inject the execution of experts in the judge method
injection = '''
        # 2.5. TIER-1.5: Dynamic API Expert Injection
        try:
            from scp.data_sources.domain_classifier import classify_top1
            domain = classify_top1(question)
            expert = self.domain_experts.get(domain)
            if expert:
                # call the expert's predict
                resp = expert.predict(question)
                if getattr(resp, 'answer', None):
                    context += f"\\n\\n[SYSTEM EXPERT DATA] For {domain}: {resp.answer}"
                    # also add to slm_responses so api_server can see it
                    if not hasattr(result, 'slm_responses'):
                        # but result is a VerifyResult which is a namedtuple or object, let's just 
                        # add it to kwargs or something?
                        pass
        except Exception as e:
            import logging
            logging.getLogger("scp.judge").debug(f"Expert injection failed: {e}")
'''

content = content.replace('elif is_structurally_pass and ai_answer:', injection.strip() + '\n        elif is_structurally_pass and ai_answer:')

with open(judge_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("Unlocked experts in judge.py")
