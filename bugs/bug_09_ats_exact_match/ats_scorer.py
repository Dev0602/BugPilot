"""Professional ATS scoring system — STRICT mode matching real ATS (Workday, Greenhouse, iCIMS)."""

import re


# ── Limited synonyms — only obvious exact-equivalents ─────────────────
SYNONYMS = {
    'javascript': ['javascript', 'js'],
    'typescript': ['typescript', 'ts'],
    'machine learning': ['machine learning', 'ml'],
    'artificial intelligence': ['artificial intelligence', 'ai'],
    'amazon web services': ['amazon web services', 'aws'],
}

BUZZWORDS = [
    'synergy', 'passionate', 'ninja', 'rockstar', 'guru', 'wizard',
    'thought leader', 'game changer', 'disruptive', 'innovative thinker',
    'results-driven', 'detail-oriented', 'team player', 'go-getter',
    'self-starter', 'dynamic', 'proactive', 'hardworking',
]

WEAK_VERBS = [
    'responsible for', 'worked on', 'helped with', 'assisted with',
    'involved in', 'participated in', 'contributed to', 'duties included',
]

STRONG_ACTION_VERBS = [
    'led', 'built', 'developed', 'designed', 'implemented', 'created',
    'managed', 'improved', 'increased', 'reduced', 'launched', 'delivered',
    'achieved', 'optimized', 'automated', 'architected', 'engineered',
    'deployed', 'integrated', 'scaled', 'mentored', 'spearheaded', 'drove',
    'established', 'streamlined', 'transformed', 'accelerated', 'generated',
]

SOFT_SKILLS = [
    'leadership', 'communication', 'teamwork', 'collaboration',
    'problem solving', 'problem-solving', 'analytical',
    'mentoring', 'cross-functional', 'stakeholder',
]


def _exact_match(keyword, resume_lower):
    """STRICT: only exact phrase match (with word boundaries)."""
    kw = keyword.lower().strip()
    pattern = r'\b' + re.escape(kw) + r'\b'
    return bool(re.search(pattern, resume_lower))


def _limited_synonym_match(keyword, resume_lower):
    """Very limited — only true equivalents like ML = Machine Learning."""
    kw = keyword.lower().strip()
    for group in SYNONYMS.values():
        if kw in group:
            for syn in group:
                pattern = r'\b' + re.escape(syn) + r'\b'
                if re.search(pattern, resume_lower):
                    return True
    return False


def _keyword_frequency(keyword, resume_lower):
    """Count how many times keyword appears — real ATS rewards repetition."""
    kw = keyword.lower().strip()
    pattern = r'\b' + re.escape(kw) + r'\b'
    return len(re.findall(pattern, resume_lower))


def calculate_ats_score(resume_text, keywords):
    """
    STRICT ATS scoring — matches real Workday/Greenhouse-style filtering.

    Weighting (total 100):
      Keywords:     50 pts (exact match only)
      Content:      25 pts (verbs + metrics + impact)
      Formatting:   15 pts (sections + structure + dates)
      Contact:       5 pts (must-have info)
      Job Fit:       5 pts (degree + title alignment)
    """

    resume_lower = resume_text.lower()
    issues = []
    completed = []

    # ═══════════════════════════════════════════════════════════════
    # CATEGORY 1: KEYWORD MATCH (max 50 pts) — STRICT
    # ═══════════════════════════════════════════════════════════════
    exact_matched = []
    synonym_matched = []
    missing = []

    for keyword in keywords:
        if _exact_match(keyword, resume_lower):
            exact_matched.append(keyword)
        elif _limited_synonym_match(keyword, resume_lower):
            synonym_matched.append(keyword)
        else:
            missing.append(keyword)

    total_kw = len(keywords) if keywords else 1

    # Synonyms only get 30% credit (real ATS gives 0% for synonyms)
    kw_ratio = (len(exact_matched) + len(synonym_matched) * 0.3) / total_kw
    keyword_score = kw_ratio * 50

    # PENALTY: if more than 30% of keywords missing → harsh deduction
    miss_ratio = len(missing) / total_kw
    if miss_ratio > 0.5:
        keyword_score = max(0, keyword_score - 10)  # extra penalty
        issues.append({
            'category': 'Keywords',
            'issue': f'CRITICAL: {len(missing)}/{total_kw} keywords missing ({int(miss_ratio*100)}%)',
            'impact': 'high',
            'fix': f'Add ALL of these keywords exactly as written: {", ".join(missing[:8])}'
        })
    elif miss_ratio > 0.3:
        issues.append({
            'category': 'Keywords',
            'issue': f'{len(missing)} important keywords missing',
            'impact': 'high',
            'fix': f'Add these keywords: {", ".join(missing[:5])}{"..." if len(missing) > 5 else ""}'
        })
    elif len(missing) > 0:
        issues.append({
            'category': 'Keywords',
            'issue': f'{len(missing)} keywords missing',
            'impact': 'medium',
            'fix': f'Add: {", ".join(missing[:3])}'
        })
    else:
        completed.append({'category': 'Keywords', 'check': 'All keywords matched exactly', 'points': 50})

    # BONUS: keyword density check — real ATS rewards repetition
    high_freq_count = sum(1 for kw in exact_matched
                          if _keyword_frequency(kw, resume_lower) >= 2)
    if high_freq_count < len(exact_matched) * 0.3:
        issues.append({
            'category': 'Keywords',
            'issue': 'Most keywords mentioned only once',
            'impact': 'medium',
            'fix': 'Repeat important keywords 2-3 times across resume for better ATS ranking'
        })

    # ═══════════════════════════════════════════════════════════════
    # CATEGORY 2: CONTENT QUALITY (max 25 pts) — STRICTER
    # ═══════════════════════════════════════════════════════════════
    content_score = 0

    # Action verbs (8 pts) — need at least 8 to get full points
    verbs_found = [v for v in STRONG_ACTION_VERBS if v in resume_lower]
    verb_score = min(len(verbs_found) / 8, 1.0) * 8
    content_score += verb_score

    if len(verbs_found) < 5:
        issues.append({
            'category': 'Content Quality',
            'issue': f'Only {len(verbs_found)} strong action verbs (need 8+)',
            'impact': 'high',
            'fix': 'Start EVERY bullet with: Led, Built, Engineered, Designed, Deployed, Optimized'
        })
    elif len(verbs_found) >= 8:
        completed.append({'category': 'Content Quality', 'check': f'{len(verbs_found)} action verbs', 'points': 8})

    # Weak verb penalty — harsher
    weak_found = [w for w in WEAK_VERBS if w in resume_lower]
    if weak_found:
        content_score = max(0, content_score - len(weak_found) * 2.5)
        issues.append({
            'category': 'Content Quality',
            'issue': f'WEAK PHRASES: {", ".join(weak_found[:3])}',
            'impact': 'high',
            'fix': 'Replace "responsible for" → "Led". Replace "worked on" → "Built"'
        })

    # Measurable results (12 pts) — need 5+ for full points
    number_patterns = [
        r'\d+%',
        r'\$[\d,]+',
        r'\d+x\b',
        r'\b\d+\+?\s*(users|customers|clients|requests|engineers|applications|projects)',
        r'\b\d+\+?\s*(million|billion|thousand|hundred)',
        r'\b\d+\s*(hours|days|weeks|months|years)',
        r'\b\d+\s*(ms|seconds|minutes)',
    ]
    results_found = sum(1 for p in number_patterns
                        if re.search(p, resume_text, re.IGNORECASE))
    results_score = min(results_found / 5, 1.0) * 12
    content_score += results_score

    if results_found < 4:
        issues.append({
            'category': 'Content Quality',
            'issue': f'Only {results_found} measurable achievements (need 5+)',
            'impact': 'high',
            'fix': 'Add numbers to EVERY bullet: "Increased by 40%", "Served 1,000+ users", "Reduced latency by 200ms"'
        })
    elif results_found >= 5:
        completed.append({'category': 'Content Quality', 'check': f'{results_found} measurable achievements', 'points': 12})

    # Buzzword penalty
    buzzwords_found = [b for b in BUZZWORDS if b in resume_lower]
    if buzzwords_found:
        content_score = max(0, content_score - len(buzzwords_found) * 3)
        issues.append({
            'category': 'Content Quality',
            'issue': f'BUZZWORDS FOUND: {", ".join(buzzwords_found[:3])}',
            'impact': 'medium',
            'fix': 'Remove buzzwords. Replace "passionate developer" → specific achievement'
        })

    # Personal pronoun penalty
    pronoun_pattern = r'\b(me|my|myself|we|our)\b'
    pronouns_found = len(re.findall(pronoun_pattern, resume_text, re.IGNORECASE))
    pronouns_found += len(re.findall(
        r'\bI\s+(am|was|have|had|will|would|did|do|can|could|should)\b', resume_text))
    if pronouns_found > 0:
        content_score = max(0, content_score - pronouns_found * 1.5)
        if pronouns_found > 2:
            issues.append({
                'category': 'Content Quality',
                'issue': f'Personal pronouns: {pronouns_found} instances',
                'impact': 'medium',
                'fix': 'Remove "I", "me", "my", "we", "our". Use action verbs directly.'
            })

    # Soft skills (5 pts) — need 3+ for full points
    soft_found = [s for s in SOFT_SKILLS if s in resume_lower]
    soft_score = min(len(soft_found) / 3, 1.0) * 5
    content_score += soft_score

    content_score = max(0, min(content_score, 25))

    # ═══════════════════════════════════════════════════════════════
    # CATEGORY 3: FORMATTING (max 15 pts) — STRICT
    # ═══════════════════════════════════════════════════════════════
    format_score = 0

    # Standard sections (6 pts)
    standard_sections = ['experience', 'education', 'skills', 'projects']
    sections_found = [s for s in standard_sections if s in resume_lower]
    section_score = (len(sections_found) / len(standard_sections)) * 6
    format_score += section_score

    missing_sections = [s for s in standard_sections if s not in resume_lower]
    if missing_sections:
        issues.append({
            'category': 'Formatting',
            'issue': f'Missing sections: {", ".join(missing_sections)}',
            'impact': 'high',
            'fix': f'Add: {", ".join(s.title() for s in missing_sections)}'
        })
    else:
        completed.append({'category': 'Formatting', 'check': 'All standard sections present', 'points': 6})

    # Bullet points (5 pts) — STRICT: need 10+
    bullet_count = len(re.findall(r'[•\-\*]\s', resume_text))
    if bullet_count >= 10:
        format_score += 5
        completed.append({'category': 'Formatting', 'check': f'{bullet_count} bullets', 'points': 5})
    elif bullet_count >= 6:
        format_score += 3
        issues.append({
            'category': 'Formatting',
            'issue': f'Only {bullet_count} bullets (need 10+)',
            'impact': 'medium',
            'fix': 'Use bullet points for every responsibility'
        })
    else:
        issues.append({
            'category': 'Formatting',
            'issue': f'Insufficient bullets ({bullet_count})',
            'impact': 'high',
            'fix': 'Format ALL experience with bullet points starting with action verbs'
        })

    # Dates (4 pts)
    date_pattern = r'\b(20\d\d|19\d\d)\b'
    dates_found = re.findall(date_pattern, resume_text)
    if len(dates_found) >= 4:
        format_score += 4
        completed.append({'category': 'Formatting', 'check': 'Dates present', 'points': 4})
    elif len(dates_found) >= 2:
        format_score += 2
    else:
        issues.append({
            'category': 'Formatting',
            'issue': 'Missing dates',
            'impact': 'high',
            'fix': 'Add Month + Year for every position (e.g. Jan 2023 - May 2024)'
        })

    # ═══════════════════════════════════════════════════════════════
    # CATEGORY 4: CONTACT INFO (max 5 pts) — minimal weight
    # ═══════════════════════════════════════════════════════════════
    contact_score = 0

    if re.search(r'[\w\.-]+@[\w\.-]+\.\w+', resume_text):
        contact_score += 2
        completed.append({'category': 'Contact Info', 'check': 'Email present', 'points': 2})
    else:
        issues.append({'category': 'Contact Info', 'issue': 'No email', 'impact': 'high', 'fix': 'Add email'})

    if re.search(r'[\+\(]?[\d\s\-\(\)]{10,}', resume_text):
        contact_score += 1
        completed.append({'category': 'Contact Info', 'check': 'Phone present', 'points': 1})

    if 'linkedin' in resume_lower:
        contact_score += 1
        completed.append({'category': 'Contact Info', 'check': 'LinkedIn present', 'points': 1})
    else:
        issues.append({'category': 'Contact Info', 'issue': 'No LinkedIn', 'impact': 'medium', 'fix': 'Add LinkedIn URL'})

    if 'github' in resume_lower:
        contact_score += 1
        completed.append({'category': 'Contact Info', 'check': 'GitHub present', 'points': 1})

    # ═══════════════════════════════════════════════════════════════
    # CATEGORY 5: JOB FIT (max 5 pts) — minimal weight
    # ═══════════════════════════════════════════════════════════════
    fit_score = 0

    title_keywords = ['engineer', 'developer', 'manager', 'analyst', 'scientist',
                      'designer', 'architect', 'lead', 'senior', 'intern']
    if any(t in resume_lower for t in title_keywords):
        fit_score += 2

    edu_keywords = ['bachelor', 'master', 'phd', 'degree', 'university',
                    'b.s', 'b.tech', 'm.tech', 'computer science']
    edu_found = sum(1 for e in edu_keywords if e in resume_lower)
    if edu_found >= 2:
        fit_score += 3
        completed.append({'category': 'Job Fit', 'check': 'Education + title', 'points': 5})
    elif edu_found >= 1:
        fit_score += 2

    # ═══════════════════════════════════════════════════════════════
    # FINAL SCORE
    # ═══════════════════════════════════════════════════════════════
    raw_score = keyword_score + content_score + format_score + contact_score + fit_score
    final_score = max(0, min(int(raw_score), 100))

    # Sort issues by impact
    impact_order = {'high': 0, 'medium': 1, 'low': 2}
    issues.sort(key=lambda x: impact_order.get(x['impact'], 3))

    return {
        'score': final_score,
        'matched_keywords': exact_matched + synonym_matched,
        'missing_keywords': missing,
        'issues': issues,
        'completed': completed,
        'breakdown': {
            'keyword_match': round(keyword_score),
            'content_quality': round(content_score),
            'formatting': round(format_score),
            'contact_info': round(contact_score),
            'job_fit': round(fit_score),
        }
    }