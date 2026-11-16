"""Proposed resume intervention: preserve claim blocks, honor preferences, scope review."""
import re

from evaluation.resume_case import BASELINE


def tailor_blocks(source, requirements, education_first=False, preserve_wording=False):
    rows = [{'source_line': i, 'before': line, 'after': line}
            for i, line in enumerate(source.splitlines(), 1) if line.strip()]
    labels = {r['label'] for r in requirements}
    if not preserve_wording:
        for row in rows:
            if BASELINE.NEGATIVE.search(row['before']):
                continue
            for label, regex, replacement in BASELINE.REWRITES:
                if label in labels:
                    row['after'] = re.sub(regex, replacement or (lambda m: 'REST API endpoint' +
                                         ('s' if m.group().lower().endswith('s') else '')), row['after'], flags=re.I)
    headings = BASELINE.HEADINGS | {'professional summary', 'work history', 'employment history'}
    preamble, sections, current = [], [], None
    for row in rows:
        title = row['after'].strip().strip('#: ').lower()
        if title in headings:
            current = {'title': title, 'rows': [row]}
            sections.append(current)
        elif current is None:
            preamble.append(row)
        else:
            current['rows'].append(row)

    def relevance(block):
        return sum(r['weight'] for r in requirements
                   if any(BASELINE.positive_matches(row['after'], r['aliases']) for row in block))

    bullet = re.compile(r'^\s*[-*•]\s+')
    for section in sections:
        source_rows = section['rows']
        output, group, i = [source_rows[0]], [], 1
        def flush():
            nonlocal group
            output.extend(row for block in sorted(group, key=lambda b: -relevance(b)) for row in block)
            group = []
        while i < len(source_rows):
            row = source_rows[i]
            if bullet.match(row['after']):
                block = [row]
                i += 1
                while (i < len(source_rows) and source_rows[i]['before'][:1].isspace()
                       and source_rows[i]['source_line'] == block[-1]['source_line'] + 1
                       and not bullet.match(source_rows[i]['after'])):
                    block.append(source_rows[i])
                    i += 1
                group.append(block)
            else:
                flush()
                output.append(row)
                i += 1
        flush()
        section['rows'] = output
    priority = {'summary': 0, 'professional summary': 0, 'objective': 1, 'experience': 2,
                'work experience': 2, 'professional experience': 2, 'work history': 2,
                'employment history': 2, 'technical skills': 3, 'skills': 3,
                'projects': 4, 'selected projects': 4, 'education': 5, 'certifications': 6,
                'awards': 7, 'volunteer experience': 8, 'activities': 9, 'interests': 10}
    sections.sort(key=lambda s: (0 if education_first and s['title'] == 'education' else 1,
                                 -relevance(s['rows'][1:]), priority.get(s['title'], 8)))
    ordered = preamble + [row for section in sections for row in section['rows']]
    if sorted(row['source_line'] for row in ordered) != sorted(row['source_line'] for row in rows):
        raise AssertionError('Source rows were duplicated or lost.')
    heading_ids = {s['rows'][0]['source_line'] for s in sections}
    ranks = {row['source_line']: i for i, row in enumerate(rows)}
    output, provenance = [], []
    for rank, row in enumerate(ordered):
        if output and row['source_line'] in heading_ids:
            output.append('')
        output.append(row['after'])
        provenance.append({**row, 'output_line': len(output), 'rewritten': row['before'] != row['after'],
                           'moved': ranks[row['source_line']] != rank,
                           'reason': 'Move whole claim blocks with continuations; honor explicit wording and section-order preferences.'})
    return '\n'.join(output) + '\n', provenance


def build_comparison(source, jd, job_id='custom', filename='resume.txt', preferences=None):
    preferences = preferences or {}
    allowed = {'education_first', 'preserve_wording'}
    if any(key not in allowed or not isinstance(value, bool) for key, value in preferences.items()):
        raise ValueError('Resume preferences must be named booleans: education_first and preserve_wording.')
    report = BASELINE.build_comparison(source, jd, job_id, filename)
    requirements = BASELINE.requirements_from_jd(jd)
    tailored, provenance = tailor_blocks(source, requirements, **preferences)
    after = BASELINE.score_resume(tailored, requirements)
    report.update(version='source-block-preferences-v2', tailored_text=tailored,
                  tailored_sha256=BASELINE.sha256(tailored.encode()), after=after,
                  delta=round(after['score'] - report['before']['score'], 2), provenance=provenance,
                  changes=[row for row in provenance if row['moved'] or row['rewritten']],
                  preferences={name: preferences.get(name, False) for name in sorted(allowed)},
                  unmet_requirements=[r['label'] for r in after['requirements'] if not r['matched']])
    report['score_interpretation'] = (f"Presentation/relevance index {report['before']['score']:.2f} → {after['score']:.2f}; "
                                    f"qualification coverage {report['before']['coverage_percent']:.2f}% → {after['coverage_percent']:.2f}%. "
                                    'Ordering can change prominence, not candidate qualifications. User constraints take priority over maximizing this index.')
    report['limitations'] += ' Wrapped, indented continuation lines stay with their claim block. Wording/order preferences are explicit controls. This remains a lexical diagnostic, not a general semantic verifier.'
    return report


def study_html(original):
    """Keep the same task/page while adding the proposed preference and review controls."""
    preferences = '''<fieldset><legend>Resume preferences</legend>
<label><input id="pref-education" name="education_first" type="checkbox"> Keep Education before Experience</label>
<label><input id="pref-wording" name="preserve_wording" type="checkbox"> Preserve original bullet and continuation wording exactly</label>
</fieldset><p id="review-permission" role="status">The current version needs explicit approval in the shared text channel.</p>'''
    result = original.replace('<button id="tailor"', preferences + '<button id="tailor"')
    result = result.replace('job_id:jobId,job_description:jd});',
                            "job_id:jobId,job_description:jd,preferences:{education_first:$('#pref-education').checked,preserve_wording:$('#pref-wording').checked}});")
    result = result.replace("$('#job-id').addEventListener('input', invalidate);",
                            "$('#job-id').addEventListener('input', invalidate);\n$('#pref-education').addEventListener('change', invalidate);\n$('#pref-wording').addEventListener('change', invalidate);")
    result = result.replace('<span>relevance points</span>', '<span>presentation-index points</span>')
    result = result.replace('3. Compare and review</h2>', '3. Compare and review</h2><p><strong>Presentation index:</strong> ordering affects the score; unchanged coverage means unchanged qualifications. Review your constraints before optimizing the score.</p>')
    result = result.replace("text('#before-text',r.source_text);", "text('#method',(r.score_interpretation||'')+' '+r.method); text('#before-text',r.source_text);")
    control = '''<script>
document.querySelector('#use-tailored').disabled=true;
setInterval(async()=>{try{
 const response=await fetch('/api/review-status'); const state=await response.json();
 document.querySelector('#use-tailored').disabled=!state.approved;
 document.querySelector('#review-permission').textContent=state.approved
 ?'The current version was explicitly approved through the shared text channel.'
 :'Ask the user to approve the current version through the shared text channel before selecting the file or submitting.';
}catch(error){document.querySelector('#use-tailored').disabled=true;}},1000);
</script>'''
    return result.replace('</html>', control + '</html>')
