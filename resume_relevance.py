"""Deterministic, source-preserving resume tailoring and explainable JD scoring.

No model or network is used. All output lines retain source-line provenance.
The score measures lexical coverage and placement, not hiring suitability.
"""
import argparse
from collections import Counter
import difflib
import hashlib
import html
import io
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

VERSION = 'lexical-coverage-prominence-v1'
MAX_UPLOAD = 5 * 1024 * 1024
MAX_TEXT = 100_000
# Canonical labels and equivalent spellings; these are NOT generated candidate facts.
VOCABULARY = {
    'Python': ['python'], 'SQL': ['sql', 'structured query language'],
    'PostgreSQL': ['postgresql', 'postgres'], 'JavaScript': ['javascript', 'js'],
    'TypeScript': ['typescript'], 'Java': ['java'], 'C++': ['c++'], 'C#': ['c#'],
    'React': ['react', 'react.js', 'reactjs'], 'Node.js': ['node.js', 'nodejs'],
    'REST API': ['rest api', 'rest apis', 'rest endpoint', 'rest endpoints', 'restful api', 'restful apis'],
    'Git': ['git'], 'Docker': ['docker'], 'Kubernetes': ['kubernetes', 'k8s'],
    'AWS': ['aws', 'amazon web services'], 'Azure': ['azure'], 'Linux': ['linux'],
    'automated testing': ['automated testing', 'unit testing', 'unit tests', 'pytest'],
    'CI/CD': ['ci/cd', 'continuous integration', 'github actions'],
    'data analysis': ['data analysis', 'data analytics'], 'Excel': ['excel'],
    'Tableau': ['tableau'], 'Power BI': ['power bi'], 'pandas': ['pandas'],
    'machine learning': ['machine learning'], 'communication': ['communication'],
    'collaboration': ['collaboration', 'collaborated', 'collaborate'],
    'customer service': ['customer service'], 'project management': ['project management'],
}
HEADINGS = {'summary', 'objective', 'education', 'experience', 'work experience',
            'professional experience', 'projects', 'selected projects', 'skills',
            'technical skills', 'interests', 'activities', 'certifications',
            'volunteer experience', 'additional experience', 'awards'}
NEGATIVE = re.compile(r"\b(no|not|never|without|lack(?:s|ing)?|unfamiliar|learning|aspiring|interested in|want to learn)\b", re.I)
REWRITES = [('JavaScript', r'\bJS\b', 'JavaScript'),
            ('PostgreSQL', r'\bPostgres\b', 'PostgreSQL'),
            ('Kubernetes', r'\bk8s\b', 'Kubernetes'),
            ('REST API', r'\bREST endpoints?\b', None)]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def extract_text(filename, raw):
    """Read UTF-8 TXT, text PDF, or DOCX; fail explicitly on unreadable inputs."""
    if not raw or len(raw) > MAX_UPLOAD:
        raise ValueError('Upload a nonempty resume no larger than 5 MiB.')
    suffix = Path(filename).suffix.lower()
    if suffix == '.txt':
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('TXT resumes must use UTF-8 encoding.') from exc
    elif suffix == '.pdf':
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError('PDF support requires: pip install -r requirements-resume.txt') from exc
        try:
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted or len(reader.pages) > 50:
                raise ValueError('Use an unencrypted PDF of at most 50 pages.')
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('Could not read this PDF. Export a text PDF or UTF-8 TXT.') from exc
    elif suffix == '.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if sum(info.file_size for info in archive.infolist()) > 20 * 1024 * 1024:
                    raise ValueError('DOCX expanded contents exceed 20 MiB.')
                root = ElementTree.fromstring(archive.read('word/document.xml'))
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text = '\n'.join(''.join(t.text or '' for t in p.findall('.//w:t', ns))
                             for p in root.findall('.//w:p', ns))
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            raise ValueError('Could not read this DOCX. Export UTF-8 TXT instead.') from exc
    else:
        raise ValueError('Supported resume formats: .txt, .pdf, .docx. Export legacy .doc to one of these.')
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text or len(text) > MAX_TEXT or '\x00' in text:
        raise ValueError('Resume text is empty, unreadable, or too long. Scanned PDFs need OCR first.')
    return text + '\n'


def pattern(alias):
    return re.compile(r'(?<![\w+#])' + re.escape(alias) + r'(?![\w+#])', re.I)


def positive_matches(line, aliases):
    # Conservative clause-level filtering: uncertain/negative claims earn no credit.
    matches = []
    for clause in re.split(r';|[.!?](?:\s+|$)|,\s*(?=but\b|without\b)|\bbut\b', line):
        if NEGATIVE.search(clause):
            continue
        for alias in aliases:
            matches.extend(m.group() for m in pattern(alias).finditer(clause))
    # Node.js and other dotted names must remain matchable as a whole.
    if not NEGATIVE.search(line):
        for alias in aliases:
            matches.extend(m.group() for m in pattern(alias).finditer(line))
    return sorted(set(matches), key=str.casefold)


def requirements_from_jd(jd):
    if not isinstance(jd, str) or not jd.strip() or len(jd) > 30_000:
        raise ValueError('Provide a job description between 1 and 30,000 characters.')
    requirements = []
    for label, aliases in VOCABULARY.items():
        lines = [line for line in jd.splitlines() if positive_matches(line, aliases)]
        if lines:
            weight = 2 if any(re.search(r'\b(required|must|essential)\b', line, re.I) for line in lines) else 1
            requirements.append({'label': label, 'aliases': aliases, 'weight': weight})
    if not requirements:
        raise ValueError('No supported requirements found in this JD. This prototype scores the documented skill vocabulary; it does not infer arbitrary requirements.')
    return requirements


def score_resume(text, requirements):
    lines = [(i, line) for i, line in enumerate(text.splitlines(), 1) if line.strip()]
    total_weight = sum(r['weight'] for r in requirements)
    if not total_weight:
        raise ValueError('At least one positive-weight requirement is needed.')
    evidence, covered, prominence = [], 0, 0.0
    for req in requirements:
        hits = [(rank, number, line, positive_matches(line, req['aliases']))
                for rank, (number, line) in enumerate(lines)
                if positive_matches(line, req['aliases'])]
        first = hits[0] if hits else None
        position = 1 - first[0] / max(1, len(lines) - 1) if first else 0
        if first:
            covered += req['weight']
            prominence += req['weight'] * position
        evidence.append({**req, 'matched': bool(first), 'evidence_line': first[2] if first else None,
                         'line_number': first[1] if first else None,
                         'matched_spellings': first[3] if first else [],
                         'placement_credit': round(position, 4)})
    coverage = 100 * covered / total_weight
    placement = 100 * prominence / total_weight
    return {'score': round(.8 * coverage + .2 * placement, 2),
            'coverage_percent': round(coverage, 2), 'prominence_percent': round(placement, 2),
            'matched_count': sum(r['matched'] for r in evidence), 'requirement_count': len(requirements),
            'requirements': evidence}


def tailor_text(source, requirements, education_first=False, preserve_wording=False):
    from resume_claims import tailor_blocks
    return tailor_blocks(source, requirements, education_first, preserve_wording)


def build_comparison(source, jd, job_id='custom', filename='resume.txt', preferences=None):
    preferences = {} if preferences is None else preferences
    allowed = {'education_first', 'preserve_wording'}
    if not isinstance(preferences, dict) or any(k not in allowed or type(v) is not bool for k, v in preferences.items()):
        raise ValueError('Resume preferences must be named booleans: education_first and preserve_wording.')
    requirements = requirements_from_jd(jd)
    tailored, provenance = tailor_text(source, requirements, **preferences)
    before, after = score_resume(source, requirements), score_resume(tailored, requirements)
    report = {'version': 'source-block-preferences-v4', 'job_id': job_id, 'source_filename': filename,
            'source_sha256': sha256(source.encode()), 'jd_sha256': sha256(jd.encode()),
            'tailored_sha256': sha256(tailored.encode()), 'job_description': jd,
            'source_text': source, 'tailored_text': tailored,
            'before': before, 'after': after, 'delta': round(after['score'] - before['score'], 2),
            'changes': [p for p in provenance if p['moved'] or p['rewritten']],
            'provenance': provenance,
            'unmet_requirements': [r['label'] for r in after['requirements'] if not r['matched']],
            'method': 'Score = 0.8 × weighted requirement coverage + 0.2 × weighted first-evidence prominence. Prominence per match = 1 − nonblank-line rank / max(1, nonblank-line count − 1). Missing requirements receive zero. JD lines containing required/must/essential have weight 2; others weight 1. The same aliases, weights, and requirements are frozen before tailoring.',
            'limitations': 'Lexical diagnostic, not an ATS score or hiring probability. Curated vocabulary only; no inference of years, seniority, degree equivalence or semantic entailment. Negated/uncertain clauses receive no credit. Tailoring only reorders existing sections/bullets and normalizes explicit technology spellings; it cannot fill qualification gaps. Extracted PDF/DOCX layout is not preserved. Review the text and provenance before use.'}

    report['preferences'] = {name: preferences.get(name, False) for name in sorted(allowed)}
    report['score_interpretation'] = (f"Presentation/relevance index {before['score']:.2f} → {after['score']:.2f}; "
        f"qualification coverage {before['coverage_percent']:.2f}% → {after['coverage_percent']:.2f}%. "
        'Ordering can change prominence, not candidate qualifications. User constraints take priority over maximizing this index.')
    report['validation'] = {'source_rows_preserved': True, 'claim_blocks_preserved': True,
                            'verbatim_wording': all(not row['rewritten'] for row in provenance)}
    report['limitations'] += ' Indented continuations move with whole claim blocks; ambiguous unindented boundaries freeze the preceding bullet group. Identity and employer metadata are not rewritten. This is not semantic verification of arbitrary resume layouts.'
    return report


def comparison_html(report):
    e = lambda value: html.escape(str(value))
    rows = ''.join('<tr><td>' + e(a['label']) + '</td><td>' + e(a['weight']) + '</td><td>'
                   + e(a['evidence_line'] or 'Missing') + '</td><td>' + e(b['evidence_line'] or 'Missing') + '</td></tr>'
                   for a, b in zip(report['before']['requirements'], report['after']['requirements']))
    changes = ''.join('<li>Source line ' + str(c['source_line']) + ' → output line ' + str(c['output_line'])
                      + ': <del>' + e(c['before']) + '</del> → <ins>' + e(c['after']) + '</ins></li>'
                      for c in report['changes']) or '<li>No changes were needed.</li>'
    diff = difflib.HtmlDiff(wrapcolumn=64).make_table(report['source_text'].splitlines(), report['tailored_text'].splitlines(),
                                                  fromdesc='Original resume', todesc='Tailored resume')
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Resume relevance comparison</title>
<style>body{{font:16px system-ui;max-width:1200px;margin:2rem auto;padding:1rem;color:#142c35}}h1,h2{{color:#173e46}}.scores{{font-size:1.8rem;background:#edf6f4;padding:1rem;border-radius:12px}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}td,th{{padding:.5rem;border:1px solid #d2dfdf;text-align:left}}.diff{{font:12px monospace}}.diff_add,ins{{background:#d7f5df}}.diff_sub,del{{background:#ffe1df}}.diff_chg{{background:#fff1bf}}.scroll{{overflow:auto}}li{{margin:.7rem 0}}</style>
<h1>Resume relevance comparison</h1><p>Position: {e(report['job_id'])} · Method: {e(report['version'])}</p>
<p class="scores">{report['before']['score']:.2f} → {report['after']['score']:.2f} / 100 ({report['delta']:+.2f} points)</p>
<p>Requirement coverage: {report['before']['coverage_percent']:.2f}% → {report['after']['coverage_percent']:.2f}%.
Prominence: {report['before']['prominence_percent']:.2f}% → {report['after']['prominence_percent']:.2f}%.</p>
<p>{e(report['method'])}</p><p>{e(report['limitations'])}</p><h2>Requirement evidence</h2>
<table><tr><th>Requirement</th><th>Weight</th><th>Before evidence</th><th>After evidence</th></tr>{rows}</table>
<p>Unmet requirements: {e(', '.join(report['unmet_requirements']) or 'None in the extracted vocabulary')}.</p>
<h2>What changed</h2><ul>{changes}</ul><h2>Before and after</h2><div class="scroll">{diff}</div>
<h2>Job description</h2><pre style="white-space:pre-wrap">{e(report['job_description'])}</pre></html>'''


def write_artifacts(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in [('original_resume.txt', report['source_text']), ('tailored_resume.txt', report['tailored_text']),
                       ('job_description.txt', report['job_description']), ('comparison.html', comparison_html(report))]:
        (directory / name).write_bytes(text.encode('utf-8'))
    (directory / 'comparison.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    (directory / 'changes.diff').write_text(''.join(difflib.unified_diff(report['source_text'].splitlines(True),
                                            report['tailored_text'].splitlines(True), 'original_resume.txt', 'tailored_resume.txt')), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', type=Path, required=True)
    parser.add_argument('--jd', type=Path, required=True)
    parser.add_argument('--job-id', default='custom')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source = extract_text(args.resume.name, args.resume.read_bytes())
    report = build_comparison(source, args.jd.read_text(encoding='utf-8'), args.job_id, args.resume.name)
    write_artifacts(report, args.output_dir)
    print(f"Relevance: {report['before']['score']:.2f} -> {report['after']['score']:.2f} ({report['delta']:+.2f}); {args.output_dir / 'comparison.html'}")


if __name__ == '__main__':
    main()

