"""Collect direct human probes after an actual human-mode study session."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--preview', action='store_true', help='Print the probes without recording anything (rehearsals and demos).')
    args = parser.parse_args()
    config = json.loads((args.run / 'config.json').read_text())
    registry = json.loads((ROOT / 'evaluation/core_metrics.json').read_text())
    if args.preview:
        for item in registry['subjective_human_only'].values():
            print(item['question'] + f" (1={item['anchors'][0]}, 7={item['anchors'][1]})")
        print('Then the interviewer follows the case interview_template.md and types notes, ending with END.')
        print('Preview only: nothing was recorded.')
        return
    if config.get('phase') == 'rehearsal':
        parser.error('This run is a technical rehearsal, not a participant session; nothing is recorded.')
    if config['mode'] != 'human':
        parser.error('Subjective metrics can only be collected from a person after a human-mode run.')
    if any((args.run / name).exists() for name in ('survey.json', 'interview_notes.md')):
        parser.error('Feedback already exists; preserve the original responses.')
    answers = {}
    for name, item in registry['subjective_human_only'].items():
        while True:
            raw = input(item['question'] + f" (1={item['anchors'][0]}, 7={item['anchors'][1]}): ")
            try:
                value = int(raw)
                if 1 <= value <= 7:
                    answers[name] = value
                    break
            except ValueError:
                pass
            print('Please enter an integer from 1 to 7; stop the recorder if the participant declines.')
    survey = {'schema_version': 'team-core-v1', 'respondent_type': 'human', 'run_id': config['run_id'],
              'timestamp': datetime.now(timezone.utc).isoformat(), 'answers': answers}
    (args.run / 'survey.json').write_text(json.dumps(survey, indent=2), encoding='utf-8')
    print('Enter interviewer notes or direct participant quotes, one line at a time. Enter END to finish.')
    lines = []
    while True:
        line = input()
        if line == 'END':
            break
        lines.append(line)
    (args.run / 'interview_notes.md').write_text('# Human interview notes\n\nRun: ' + config['run_id'] + '\n\n' + '\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
