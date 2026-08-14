from ats_scorer import _exact_match

def test_exact_match_respects_word_boundaries():
    resume_text = "Used jsonify to build APIs efficiently."
    assert _exact_match("js", resume_text) == False

def test_exact_match_finds_real_keyword():
    resume_text = "Built applications using javascript and react."
    assert _exact_match("javascript", resume_text) == True