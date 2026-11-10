import json
from datasets import load_dataset
from swebench_batch_solve import retry_with_feedback, ensure_repo, get_target_file
import subprocess
import re
import os

INSTANCE_ID = "django__django-11019"

ERROR_OUTPUT = """
ERROR: test_merge (forms_tests.tests.test_media.FormsMediaTestCase) (lists=([1, 2], [3, 4]))
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/testbed/tests/forms_tests/tests/test_media.py", line 553, in test_merge
    self.assertEqual(Media.merge(*lists), expected)
  File "/testbed/django/forms/widgets.py", line 127, in merge
    dependency_graph = defaultdict(set)
NameError: name 'defaultdict' is not defined
"""

with open("bugpilot_batch_predictions.json") as f:
    predictions = json.load(f)

previous_pred = next(p for p in predictions if p["instance_id"] == INSTANCE_ID)

ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
instance = next(r for r in ds if r["instance_id"] == INSTANCE_ID)

# Reconstruct the previous diagnosis/function_name/fixed_function_code
# from the diff we already generated (since predictions only stores the
# final patch, not the intermediate fields) - so let's just re-solve
# fresh, but this time pretend the retry context replaces the initial one.
previous_result = {
    "diagnosis": "Previous fix used defaultdict without importing it.",
    "function_name": "Media.merge",
    "fixed_function_code": "(see previous patch.diff for full previous attempt)",
}

result = retry_with_feedback(instance, previous_result, ERROR_OUTPUT)

if not result:
    print("Retry failed to produce a usable result.")
else:
    print("New diagnosis:", result["diagnosis"])
    print("\nNew fixed code:\n", result["fixed_function_code"])

    with open("swebench_retry_result.json", "w") as f:
        json.dump(result, f, indent=2)
    print("\nSaved to swebench_retry_result.json")