import os
import re

judge_file = r'scp\runtime\judge.py'
with open(judge_file, 'r', encoding='utf-8') as f:
    content = f.read()

# I need to find where the injection happens, and also pass slm_responses to the return dict.
# Let's just redefine the injection to create an slm_responses list and add it to a local variable.

injection_fixed = '''
        slm_responses_list = []
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
                    # convert SLMResponse to dict so DotDict doesn't choke or api_server can process it
                    slm_responses_list.append(resp.__dict__)
        except Exception as e:
            import logging
            logging.getLogger("scp.judge").debug(f"Expert injection failed: {e}")
'''

# Wait, previously I injected:
#         # 2.5. TIER-1.5: Dynamic API Expert Injection
# Let's replace the old injection with this new one.

old_injection = r'# 2\.5\. TIER-1\.5: Dynamic API Expert Injection.*?logging\.getLogger\("scp\.judge"\)\.debug\(f"Expert injection failed: \{e\}"\)'

content = re.sub(old_injection, injection_fixed.strip(), content, flags=re.DOTALL)

# Now, we need to make sure the return dict includes 'slm_responses': slm_responses_list
# There are two return statements: one for escalated, one for normal.

# Find the return dicts and add 'slm_responses': slm_responses_list,
content = re.sub(r'("final_answer": ai_answer,)', r'\1\n            "slm_responses": slm_responses_list,', content)

with open(judge_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated judge.py with slm_responses_list")
