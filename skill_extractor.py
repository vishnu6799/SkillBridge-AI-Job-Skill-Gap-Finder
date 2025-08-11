# skill_extractor.py
import re
import json
from pathlib import Path
import pandas as pd
import pdfplumber
from difflib import get_close_matches

# ---------------------------
# CSV loader that tolerates messy headers
# ---------------------------
def load_job_skills(job_skills_csv="job_skills.csv"):
    df = pd.read_csv(job_skills_csv, dtype=str)
    # fix common problem: header combined into one string "role,skills"
    if 'role,skills' in df.columns:
        df[['role','skills']] = df['role,skills'].astype(str).str.split(',',1,expand=True)
        df.drop(columns=['role,skills'], inplace=True)
    # if columns are unnamed, try to set first two columns as role & skills
    if 'role' not in df.columns or 'skills' not in df.columns:
        cols = df.columns.tolist()
        if len(cols) >= 2:
            df = df.rename(columns={cols[0]:'role', cols[1]:'skills'})
        else:
            raise ValueError("job_skills.csv must have at least two columns (role, skills).")
    # fillna
    df['role'] = df['role'].astype(str).str.strip()
    df['skills'] = df['skills'].astype(str).str.strip()
    return df

# ---------------------------
# Build vocabulary from CSV + resources.json
# ---------------------------
def build_skill_vocabulary(job_skills_csv="job_skills.csv", resources_json="resources.json"):
    df = load_job_skills(job_skills_csv)
    skills = set()
    for s in df['skills'].dropna():
        parts = [x.strip() for x in re.split(r'[;,]', str(s))]
        skills.update(parts)
    try:
        with open(resources_json, 'r', encoding='utf-8') as f:
            res = json.load(f)
        skills.update(res.keys())
    except Exception:
        pass
    # normalize
    skills = sorted({s for s in skills if s and isinstance(s, str)})
    return skills

# ---------------------------
# Text extraction helpers
# ---------------------------
def extract_text_from_pdf(path):
    text = ""
    try:
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                t = p.extract_text()
                if t:
                    text += t + "\n"
    except Exception:
        pass
    return text

def extract_text_from_txt(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ""

# ---------------------------
# Skill matching: exact + fuzzy
# ---------------------------
def extract_skills_from_text(text, vocabulary, fuzzy_cutoff=0.85):
    if not text or not vocabulary:
        return []
    text_lower = text.lower()
    found = set()
    # exact matches
    for skill in vocabulary:
        pattern = r'\b' + re.escape(skill.lower()) + r'\b'
        if re.search(pattern, text_lower):
            found.add(skill)
    # fuzzy fallback: candidate ngrams
    words = re.findall(r"[A-Za-z0-9\+\#\.\-]+", text)
    candidates = set()
    for i in range(len(words)):
        candidates.add(words[i])
        if i+1 < len(words):
            candidates.add(words[i] + " " + words[i+1])
        if i+2 < len(words):
            candidates.add(words[i] + " " + words[i+1] + " " + words[i+2])
    lower_vocab = [v.lower() for v in vocabulary]
    for cand in candidates:
        matches = get_close_matches(cand.lower(), lower_vocab, n=1, cutoff=fuzzy_cutoff)
        if matches:
            matched_lower = matches[0]
            # map back to original vocab casing
            for v in vocabulary:
                if v.lower() == matched_lower:
                    found.add(v)
                    break
    return sorted(found)

def extract_skills_from_file(path, vocabulary=None):
    if vocabulary is None:
        vocabulary = build_skill_vocabulary()
    path = str(path)
    if path.lower().endswith('.pdf'):
        text = extract_text_from_pdf(path)
    else:
        text = extract_text_from_txt(path)
    if not text.strip():
        return []
    return extract_skills_from_text(text, vocabulary)

# ---------------------------
# Role comparison & prioritized missing skills
# ---------------------------
def compare_to_role(user_skills, role_name, job_skills_csv="job_skills.csv"):
    df = load_job_skills(job_skills_csv)
    row = df[df['role'].str.lower() == role_name.lower()]
    if row.empty:
        return {"error":"Role not found", "available_roles": df['role'].tolist()}
    required = [s.strip() for s in re.split(r'[;,]', row.iloc[0]['skills'])]
    matched = [s for s in required if s in user_skills]
    missing = [s for s in required if s not in user_skills]
    # simple priority: missing sorted by frequency across roles (rare skills get higher priority)
    # compute frequency across df
    skill_counts = {}
    for slist in df['skills'].dropna():
        for s in [x.strip() for x in re.split(r'[;,]', slist)]:
            skill_counts[s] = skill_counts.get(s, 0) + 1
    # lower count -> more niche -> higher priority
    missing_sorted = sorted(missing, key=lambda x: (skill_counts.get(x,0), required.index(x)))
    return {"required": required, "matched": matched, "missing": missing_sorted}

# ---------------------------
# Generate deterministic 30-day micro learning plan (no external APIs)
# ---------------------------
def generate_microplan_for_skill(skill):
    # deterministic template per skill
    plan = []
    plan.append(f"Week 1 — Foundations: Read one introductory article and watch one tutorial about {skill}. Practice 30–60 minutes daily.")
    plan.append(f"Week 2 — Hands-on: Complete 2 small hands-on exercises or tutorials related to {skill}. Create a tiny one-page note or snippet.")
    plan.append(f"Week 3 — Build: Integrate {skill} into a mini-project or small example. Use free datasets or examples.")
    plan.append(f"Week 4 — Polish & Showcase: Prepare a 1-page summary and a short demo (video/screenshots) showing what you learned in {skill}.")
    return plan

def generate_microplans(skills):
    return {s: generate_microplan_for_skill(s) for s in skills}
