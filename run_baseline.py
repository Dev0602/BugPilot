from baseline import baseline_fix

bugs = [
        ("bugs/bug_01_calculator", "calculator.py"),
        ("bugs/bug_02_discount", "calculator.py"),
        ("bugs/bug_03_grade", "calculator.py"),
        ("bugs/bug_04_reverse", "calculator.py"),
        ("bugs/bug_05_sum_range", "calculator.py"),
        ("bugs/bug_06_mutable_default", "calculator.py"),
        ("bugs/bug_07_word_count", "calculator.py"),
        ("bugs/bug_08_factorial", "calculator.py"),
        ("bugs/bug_09_ats_exact_match", "ats_scorer.py"),
        ("bugs/bug_10_prime_checker", "calculator.py"),
        ("bugs/bug_11_safe_divide", "calculator.py"),
        ("bugs/bug_12_invalid_input", "calculator.py"),
        ("bugs/bug_13_list_index", "list_utils.py"),
        ("bugs/bug_14_dictionary", "user_utils.py"),
        ("bugs/bug_15_sets", "set_utils.py"),
        ("bugs/bug_16_string_processing", "string_utils.py"),
        ("bugs/bug_17_recursion", "factorial.py"),
        ("bugs/bug_18_algorithm", "search.py"),
        ("bugs/bug_19_empty_input", "data_utils.py"),
        ("bugs/bug_20_buzzword_detection", "text_utils.py"),
    ]

results = []
for bug_dir, filename in bugs:
    print(f"Running baseline on {bug_dir}...")
    results.append(baseline_fix(bug_dir, filename))
    
print("\n===== BASELINE RESULTS =====")
for r in results:
    status = " PASSED" if r["success"] else " FAILED"
    print(f"{r['bug']}: {status}")

successes = sum(1 for r in results if r["success"])
print(f"\nBaseline: {successes}/{len(results)} fixed ({successes/len(results)*100:.0f}%)")