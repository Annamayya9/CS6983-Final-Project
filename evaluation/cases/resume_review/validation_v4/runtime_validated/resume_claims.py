"""Proposed resume intervention: preserve claim blocks, honor preferences, scope review."""
import re

import resume_relevance as BASELINE


def tailor_blocks(source, requirements, education_first=False, preserve_wording=False):
    rows = [{'source_line': i, 'before': line, 'after': line}
            for i, line in enumerate(source.splitlines(), 1) if line.strip()]
    labels = {r['label'] for r in requirements}
    # Only technical claim lines and skills lists are eligible for canonical spelling.
    # Identity, employer, project and date metadata remain byte-for-byte unchanged.
    section_name = ''
    previous_claim_line = None
    for row in rows:
        title = row['before'].strip().strip('#: ').lower()
        if title in BASELINE.HEADINGS | {'professional summary', 'work history', 'employment history'}:
            section_name = title
        is_bullet = bool(re.match(r'^\s*[-*•]\s+', row['before']))
        continuation = bool(row['before'][:1].isspace() and previous_claim_line == row['source_line'] - 1)
        technical = is_bullet or continuation or section_name in {'skills', 'technical skills'}
        previous_claim_line = row['source_line'] if is_bullet or continuation else None
        if preserve_wording or not technical or BASELINE.NEGATIVE.search(row['before']):
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
        def flush(allow_sort=True):
            nonlocal group
            output.extend(row for block in (sorted(group, key=lambda b: -relevance(b)) if allow_sort else group) for row in block)
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
                # An unindented continuation is ambiguous with a metadata line.
                # Freeze the preceding group rather than moving its qualifier.
                flush(allow_sort=not group or row['source_line'] != group[-1][-1]['source_line'] + 1)
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
    positions = {row['source_line']: i for i, row in enumerate(ordered)}
    # Validate adjacency independently of the sorting procedure. No indented
    # qualifier is allowed to become another bullet's evidence.
    previous_claim_line = None
    for row in rows:
        if re.match(r'^\s*[-*•]\s+', row['before']):
            previous_claim_line = row['source_line']
        elif row['before'][:1].isspace() and previous_claim_line == row['source_line'] - 1:
            if positions[row['source_line']] != positions[previous_claim_line] + 1:
                raise AssertionError('A claim continuation was detached.')
            previous_claim_line = row['source_line']
        else:
            previous_claim_line = None
    if preserve_wording and any(row['before'] != row['after'] for row in ordered):
        raise AssertionError('Verbatim preference was violated.')
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

